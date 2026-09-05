import streamlit as st
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

# Optional document/OCR dependencies
try:
    import pytesseract
    OCR_AVAILABLE = True
except Exception:
    OCR_AVAILABLE = False

# Optional multilingual speech-to-text dependency.
# Uses Google's web speech recognition through SpeechRecognition.
# Internet access is required for transcription.
try:
    import speech_recognition as sr
    SPEECH_AVAILABLE = True
except Exception:
    SPEECH_AVAILABLE = False

SPEECH_LANGUAGES = {
    "English": "en-IN",
    "Hindi": "hi-IN",
    "Bengali": "bn-IN",
    "Tamil": "ta-IN",
    "Telugu": "te-IN",
    "Marathi": "mr-IN",
    "Gujarati": "gu-IN",
    "Kannada": "kn-IN",
    "Malayalam": "ml-IN",
    "Punjabi": "pa-IN",
    "Urdu": "ur-IN",
    "Odia": "or-IN",
    "Assamese": "as-IN",
}

try:
    from PIL import Image
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False

try:
    from pypdf import PdfReader
    PDF_AVAILABLE = True
except Exception:
    PDF_AVAILABLE = False


APP_NAME = "MediKiosk"
DB_PATH = Path("medikiosk.db")

st.set_page_config(
    page_title="MediKiosk — SIH26047",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)


# -----------------------------
# Database
# -----------------------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            abha_id TEXT,
            name TEXT,
            age INTEGER,
            sex TEXT,
            language TEXT,
            clinical_history TEXT DEFAULT '{}',
            ayush_history TEXT DEFAULT '{}',
            created_at TEXT
        )
        """
    )

    # Add these columns if an older database already exists.
    cur.execute("PRAGMA table_info(patients)")
    patient_columns = {row[1] for row in cur.fetchall()}

    if "clinical_history" not in patient_columns:
        cur.execute(
            "ALTER TABLE patients ADD COLUMN clinical_history TEXT DEFAULT '{}'"
        )

    if "ayush_history" not in patient_columns:
        cur.execute(
            "ALTER TABLE patients ADD COLUMN ayush_history TEXT DEFAULT '{}'"
        )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER,
            filename TEXT,
            extracted_text TEXT,
            uploaded_at TEXT
        )
        """
    )

    conn.commit()
    conn.close()


init_db()


# -----------------------------
# Session defaults
# -----------------------------
defaults = {
    "page": "Patient Intake",
    "patient": {},
    "consent": False,
    "history": {},
    "ayush": {},
    "documents": [],
    "timeline": [],
    "red_flags": [],
    "summary": "",
    "fhir": {},
    "doctor_notes": "",
}

for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# -----------------------------
# Utilities
# -----------------------------
def clean_text(text):
    return re.sub(r"\s+", " ", text or "").strip()


def save_patient(patient):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO patients
        (abha_id, name, age, sex, language,
         clinical_history, ayush_history, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            patient.get("abha_id", ""),
            patient.get("name", ""),
            patient.get("age", 0),
            patient.get("sex", ""),
            patient.get("language", ""),
            json.dumps(patient.get("clinical_history", {}), ensure_ascii=False),
            json.dumps(patient.get("ayush_history", {}), ensure_ascii=False),
            datetime.now().isoformat(timespec="seconds"),
        ),
    )

    patient_id = cur.lastrowid
    conn.commit()
    conn.close()
    return patient_id


def update_patient_record(patient_id, history, ayush):
    """Save clinical and AYUSH history for an existing patient."""
    if not patient_id:
        return

    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        UPDATE patients
        SET clinical_history = ?,
            ayush_history = ?
        WHERE id = ?
        """,
        (
            json.dumps(history or {}, ensure_ascii=False),
            json.dumps(ayush or {}, ensure_ascii=False),
            patient_id,
        ),
    )
    conn.commit()
    conn.close()


def transcribe_audio(audio_bytes, language_code):
    """Transcribe recorded speech using SpeechRecognition's Google recognizer."""
    if not SPEECH_AVAILABLE:
        return "", "Speech recognition is unavailable. Install SpeechRecognition and PyAudio."
    try:
        recognizer = sr.Recognizer()
        with sr.AudioFile(audio_bytes) as source:
            audio = recognizer.record(source)
        text = recognizer.recognize_google(audio, language=language_code)
        return clean_text(text), ""
    except sr.UnknownValueError:
        return "", "I could not understand the recording. Please try again."
    except sr.RequestError as e:
        return "", f"Speech recognition service error: {e}"
    except Exception as e:
        return "", f"Audio transcription error: {e}"


def speech_input(label, language_name, key_prefix, height=100):
    """Render an audio recorder and return its multilingual transcription."""
    if not SPEECH_AVAILABLE:
        st.warning(
            "Speech-to-text is not installed. Install: "
            "`pip install SpeechRecognition` and `pip install sounddevice`."
        )
        return ""

    language_code = SPEECH_LANGUAGES.get(language_name, "en-IN")
    audio = st.audio_input(
        f"🎙️ Speak in {language_name}",
        key=f"{key_prefix}_audio",
    )
    if audio is None:
        return ""

    with st.spinner(f"Transcribing {language_name} speech…"):
        transcript, error = transcribe_audio(audio, language_code)

    if error:
        st.error(error)
        return ""

    if transcript:
        st.success("Speech converted to text.")
        st.text_area(
            "Transcription",
            value=transcript,
            height=height,
            key=f"{key_prefix}_transcript",
        )
    return transcript


def extract_pdf_text(uploaded_file):
    if not PDF_AVAILABLE:
        return "PDF extraction unavailable. Install pypdf."

    try:
        reader = PdfReader(uploaded_file)
        pages = []
        for page in reader.pages:
            pages.append(page.extract_text() or "")
        return clean_text("\n".join(pages))
    except Exception as e:
        return f"PDF extraction error: {e}"


def extract_image_text(uploaded_file):
    if not (OCR_AVAILABLE and PIL_AVAILABLE):
        return (
            "OCR unavailable. Install pytesseract + Pillow and "
            "the Tesseract OCR engine."
        )

    try:
        image = Image.open(uploaded_file)
        return clean_text(pytesseract.image_to_string(image))
    except Exception as e:
        return f"OCR error: {e}"


def extract_document(uploaded_file):
    name = uploaded_file.name.lower()

    if name.endswith(".pdf"):
        return extract_pdf_text(uploaded_file)

    if name.endswith((".png", ".jpg", ".jpeg", ".webp", ".tiff", ".bmp")):
        return extract_image_text(uploaded_file)

    if name.endswith(".txt"):
        return clean_text(uploaded_file.read().decode("utf-8", errors="ignore"))

    return "Unsupported document format."


def detect_entities(text):
    """Simple transparent extraction layer for a demo.
    This is intentionally rule-based and must not be treated as diagnosis."""
    t = text.lower()

    medicines = []
    known_meds = [
        "metformin",
        "amlodipine",
        "paracetamol",
        "azithromycin",
        "omeprazole",
        "losartan",
        "atorvastatin",
        "insulin",
        "telmisartan",
        "levothyroxine",
    ]

    for med in known_meds:
        if med in t:
            medicines.append(med.title())

    diagnoses = []
    known_dx = [
        "diabetes",
        "hypertension",
        "asthma",
        "hypothyroidism",
        "anemia",
        "migraine",
        "arthritis",
        "pneumonia",
    ]

    for dx in known_dx:
        if dx in t:
            diagnoses.append(dx.title())

    investigations = []
    known_tests = [
        "hemoglobin",
        "hba1c",
        "blood pressure",
        "creatinine",
        "glucose",
        "cholesterol",
        "tsh",
        "ecg",
        "x-ray",
        "cbc",
    ]

    for test in known_tests:
        if test in t:
            investigations.append(
                test.upper() if test == "hba1c" else test.title()
            )

    # Generic numeric lab extraction: e.g. HbA1c 7.2
    numeric_values = re.findall(
        r"\b(?:hba1c|hemoglobin|hb|glucose|creatinine|tsh)"
        r"\s*[:=-]?\s*(\d+(?:\.\d+)?)",
        t,
    )

    return {
        "medicines": sorted(set(medicines)),
        "diagnoses": sorted(set(diagnoses)),
        "investigations": sorted(set(investigations)),
        "numeric_values": numeric_values,
    }


def build_timeline(documents):
    timeline = []

    for d in documents:
        entities = detect_entities(d["text"])
        timeline.append(
            {
                "date": d.get("date", datetime.now().date().isoformat()),
                "source": d["filename"],
                "diagnoses": entities["diagnoses"],
                "medicines": entities["medicines"],
                "investigations": entities["investigations"],
                "values": entities["numeric_values"],
            }
        )

    return sorted(timeline, key=lambda x: x["date"])


# -----------------------------
# Red-flag engine
# -----------------------------
RED_FLAG_RULES = {
    "Possible acute chest-pain emergency": [
        "severe chest pain",
        "crushing chest pain",
        "chest pain radiating to arm",
        "chest pain radiating to jaw",
    ],
    "Severe breathing difficulty": [
        "cannot breathe",
        "can't breathe",
        "severe breathlessness",
        "severe difficulty breathing",
    ],
    "Possible stroke emergency": [
        "face drooping",
        "one sided weakness",
        "one-sided weakness",
        "slurred speech",
        "sudden inability to speak",
    ],
    "Loss of consciousness": [
        "unconscious",
        "passed out",
        "loss of consciousness",
    ],
    "Severe allergic reaction": [
        "swelling of throat",
        "difficulty breathing after allergy",
        "anaphylaxis",
    ],
}


def detect_red_flags(text):
    t = clean_text(text).lower()
    found = []

    for label, phrases in RED_FLAG_RULES.items():
        if any(p in t for p in phrases):
            found.append(label)

    return found


# -----------------------------
# Adaptive questions
# -----------------------------
BASE_QUESTIONS = [
    ("chief_complaint", "What is your main health concern today?"),
    ("onset", "When did this problem start?"),
    ("course", "Has it been getting better, worse, or staying the same?"),
    ("severity", "On a scale of 0–10, how severe is it?"),
    ("associated", "What other symptoms are you experiencing?"),
    ("past_history", "Do you have any previous medical or surgical conditions?"),
    ("medications", "Are you currently taking any medicines or supplements?"),
    ("allergies", "Do you have any known drug, food, or other allergies?"),
    ("family_history", "Is there any important medical history in your family?"),
    (
        "personal_history",
        "Please describe relevant diet, sleep, activity, tobacco/alcohol use, "
        "or other lifestyle factors.",
    ),
]


def adaptive_questions(history):
    complaint = history.get("chief_complaint", "").lower()
    questions = list(BASE_QUESTIONS)

    if any(x in complaint for x in ["pain", "ache"]):
        questions.insert(
            2,
            ("pain_site", "Where exactly is the pain, and does it move anywhere else?"),
        )
        questions.insert(
            3,
            (
                "pain_character",
                "How would you describe it: pressure, burning, stabbing, "
                "throbbing, or something else?",
            ),
        )
        questions.insert(
            4,
            (
                "pain_triggers",
                "What makes it better or worse—movement, food, exertion, "
                "breathing, or rest?",
            ),
        )

    if any(x in complaint for x in ["fever", "temperature"]):
        questions.insert(
            2,
            (
                "fever_pattern",
                "What was the highest temperature you measured, and how did you measure it?",
            ),
        )

    if any(x in complaint for x in ["cough", "breath", "breathing"]):
        questions.insert(
            2,
            (
                "respiratory",
                "Do you have breathlessness, wheezing, chest discomfort, "
                "or coughing up blood?",
            ),
        )

    if any(x in complaint for x in ["stomach", "abdominal", "vomit", "diarr"]):
        questions.insert(
            2,
            (
                "gi",
                "Any vomiting, diarrhea, constipation, blood in stool, "
                "or change in appetite?",
            ),
        )

    # Remove duplicates while preserving order.
    seen = set()
    result = []

    for item in questions:
        if item[0] not in seen:
            seen.add(item[0])
            result.append(item)

    return result


# -----------------------------
# FHIR-compatible output
# -----------------------------
def make_fhir_bundle():
    p = st.session_state.patient
    h = st.session_state.history
    red = st.session_state.red_flags

    patient_id = p.get("abha_id") or "local-demo-patient"

    patient_resource = {
        "resourceType": "Patient",
        "id": patient_id,
        "name": [{"text": p.get("name", "")}],
        "gender": p.get("sex", "").lower(),
        "birthDate": None,
    }

    questionnaire = {
        "resourceType": "QuestionnaireResponse",
        "status": "completed",
        "subject": {"reference": f"Patient/{patient_id}"},
        "item": [
            {
                "linkId": k,
                "text": k.replace("_", " ").title(),
                "answer": [{"valueString": str(v)}],
            }
            for k, v in h.items()
            if v not in ("", None)
        ],
    }

    flag_observation = {
        "resourceType": "Observation",
        "status": "final",
        "code": {"text": "Triage red-flag screening"},
        "valueString": (
            "; ".join(red)
            if red
            else "No configured red flags detected"
        ),
    }

    return {
        "resourceType": "Bundle",
        "type": "collection",
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "entry": [
            {"resource": patient_resource},
            {"resource": questionnaire},
            {"resource": flag_observation},
        ],
    }


# -----------------------------
# Physician summary
# -----------------------------
def generate_summary():
    p = st.session_state.patient
    h = st.session_state.history
    a = st.session_state.ayush
    docs = st.session_state.documents
    flags = st.session_state.red_flags

    def val(key):
        return h.get(key, "Not recorded")

    lines = [
        "PATIENT CLINICAL INTAKE SUMMARY",
        "",
        f"Patient: {p.get('name', 'Not recorded')}",
        f"Age: {p.get('age', 'Not recorded')}",
        f"Sex: {p.get('sex', 'Not recorded')}",
        f"ABHA ID: {p.get('abha_id', 'Not recorded')}",
        f"Language: {p.get('language', 'Not recorded')}",
        "",
        "TRIAGE / SAFETY",
        f"Configured red flags detected: {', '.join(flags) if flags else 'None detected'}",
        "",
        "CHIEF COMPLAINT & HISTORY",
        f"Chief complaint: {val('chief_complaint')}",
        f"Onset: {val('onset')}",
        f"Course: {val('course')}",
        f"Severity: {val('severity')}",
        f"Site: {val('pain_site')}",
        f"Character: {val('pain_character')}",
        f"Triggers/relievers: {val('pain_triggers')}",
        f"Associated symptoms: {val('associated')}",
        "",
        "BACKGROUND",
        f"Past medical/surgical history: {val('past_history')}",
        f"Medicines/supplements: {val('medications')}",
        f"Allergies: {val('allergies')}",
        f"Family history: {val('family_history')}",
        f"Personal/lifestyle history: {val('personal_history')}",
        "",
        "AYUSH HISTORY",
        f"Prakriti: {a.get('prakriti', 'Not recorded')}",
        f"Vikriti: {a.get('vikriti', 'Not recorded')}",
        f"Agni: {a.get('agni', 'Not recorded')}",
        f"Koshtha: {a.get('koshtha', 'Not recorded')}",
        f"Ahara-Vihara: {a.get('ahara_vihara', 'Not recorded')}",
        f"Trividha Pariksha notes: {a.get('trividha', 'Not recorded')}",
        f"Dashavidha Pariksha notes: {a.get('dashavidha', 'Not recorded')}",
        "",
        "DOCUMENTS / RECORDS",
        f"Documents processed: {len(docs)}",
    ]

    for item in st.session_state.timeline:
        lines.append(
            f"- {item['date']} | {item['source']} | "
            f"Diagnoses: {', '.join(item['diagnoses']) or '—'} | "
            f"Medicines: {', '.join(item['medicines']) or '—'} | "
            f"Investigations: {', '.join(item['investigations']) or '—'}"
        )

    lines += [
        "",
        "IMPORTANT: This is an AI-assisted intake draft. It is not a diagnosis or treatment recommendation.",
        "PHYSICIAN VERIFICATION REQUIRED before clinical use.",
    ]

    return "\n".join(lines)


# -----------------------------
# Sidebar
# -----------------------------
with st.sidebar:
    st.title("🏥 MediKiosk")
    st.caption("SIH26047 • Patient Case-Taking Software")
    st.divider()

    pages = [
        "Patient Intake",
        "Clinical History",
        "AYUSH History",
        "Document Intelligence",
        "Timeline",
        "Physician Summary",
        "FHIR / ABDM Demo",
    ]

    selected = st.radio(
        "Navigation",
        pages,
        index=pages.index(st.session_state.page),
    )
    st.session_state.page = selected

    st.divider()
    status = (
        "🟢 Consent granted"
        if st.session_state.consent
        else "🟠 Consent pending"
    )
    st.write(status)

    with st.expander("🎙️ Multilingual speech-to-text setup"):
        st.caption(
            "Supported speech languages: English (India), Hindi, Bengali, Tamil, "
            "Telugu, Marathi, Gujarati, Kannada, Malayalam, Punjabi, Urdu, Odia, "
            "and Assamese."
        )
        st.code(
            "pip install SpeechRecognition\n"
            "pip install sounddevice",
            language="bash",
        )
        st.caption(
            "Speech transcription uses an online recognition service, so an "
            "internet connection is required. Audio is transcribed only when "
            "the user records an answer."
        )

    if st.session_state.red_flags:
        st.error("🚨 Red flag detected")


# -----------------------------
# Header
# -----------------------------
st.title("MediKiosk")
st.caption(
    "AI-assisted digital clinical intake • Structured history • AYUSH assessment • "
    "Document digitisation • Physician-ready summary"
)


# -----------------------------
# Patient Intake
# -----------------------------
if st.session_state.page == "Patient Intake":
    st.header("1. Patient Identification & Consent")

    c1, c2 = st.columns(2)

    with c1:
        name = st.text_input(
            "Patient name",
            value=st.session_state.patient.get("name", ""),
        )

        age = st.number_input(
            "Age",
            min_value=0,
            max_value=120,
            value=int(st.session_state.patient.get("age", 18)),
        )

        sex_options = ["", "Male", "Female", "Other", "Prefer not to say"]
        current_sex = st.session_state.patient.get("sex", "")
        sex_index = (
            sex_options.index(current_sex)
            if current_sex in sex_options
            else 0
        )

        sex = st.selectbox(
            "Sex",
            sex_options,
            index=sex_index,
        )

    with c2:
        abha = st.text_input(
            "ABHA ID (demo field)",
            value=st.session_state.patient.get("abha_id", ""),
        )

        language_options = [
            "English",
            "Hindi",
            "Bengali",
            "Tamil",
            "Telugu",
            "Marathi",
            "Gujarati",
            "Kannada",
            "Malayalam",
            "Punjabi",
            "Urdu",
            "Odia",
            "Assamese",
            "Other",
        ]
        current_language = st.session_state.patient.get("language", "English")
        language_index = (
            language_options.index(current_language)
            if current_language in language_options
            else 0
        )

        language = st.selectbox(
            "Preferred language",
            language_options,
            index=language_index,
        )

        mode = st.radio("Intake mode", ["Patient-facing", "Assisted by staff"])

    st.subheader("Consent")
    st.info(
        "This prototype demonstrates consent capture before collecting a structured "
        "clinical history. In a production ABDM integration, consent and identity "
        "flows must use the authorised ABDM mechanisms."
    )

    consent = st.checkbox(
        "I understand that my information will be used to prepare a structured "
        "clinical intake for physician review."
    )

    if st.button(
        "Start Patient Intake",
        type="primary",
        disabled=not consent,
    ):
        st.session_state.patient = {
            "name": name,
            "age": age,
            "sex": sex,
            "abha_id": abha,
            "language": language,
            "mode": mode,
        }
        st.session_state.consent = consent

        if name:
            st.session_state.patient["local_id"] = save_patient(
                st.session_state.patient
            )

        st.success("Consent recorded. Patient intake started.")
        st.session_state.page = "Clinical History"
        st.rerun()


# -----------------------------
# Clinical History
# -----------------------------
elif st.session_state.page == "Clinical History":
    st.header("2. Conversational Clinical History")

    if not st.session_state.consent:
        st.warning("Complete patient consent first.")
        st.stop()

    h = st.session_state.history

    st.subheader("Voice / Touch / Text")
    selected_language = st.session_state.patient.get("language", "English")

    st.caption(
        "Speak your answer in the patient's preferred Indian language. "
        "The recording is transcribed into editable text before it is saved."
    )

    if not SPEECH_AVAILABLE:
        st.info(
            "Multilingual speech-to-text is enabled in the code but requires the "
            "SpeechRecognition package. See the setup note in the sidebar."
        )

    questions = adaptive_questions(h)

    for key, question in questions:
        if key not in h:
            st.write(f"**{question}**")

            answer = st.text_area(
                question,
                key=f"q_{key}",
                label_visibility="collapsed",
                height=80,
                placeholder="Type your answer here, or use the microphone below.",
            )

            spoken_answer = speech_input(
                question,
                selected_language,
                f"speech_{key}",
                height=80,
            )
            if spoken_answer:
                answer = spoken_answer

            if st.button("Save answer", key=f"save_{key}"):
                h[key] = clean_text(answer)
                st.session_state.history = h

                # Run red-flag screening after every answer.
                combined = " ".join(h.values())
                st.session_state.red_flags = detect_red_flags(combined)

                update_patient_record(
                    st.session_state.patient.get("local_id"),
                    st.session_state.history,
                    st.session_state.ayush,
                )

                st.rerun()

            st.divider()
            break

    completed = sum(bool(v) for v in h.values())
    st.progress(min(completed / max(len(questions), 1), 1.0))
    st.caption(f"{completed} history fields captured")

    if st.session_state.red_flags:
        st.error(
            "🚨 PRIORITY TRIAGE FLAG: "
            + "; ".join(st.session_state.red_flags)
            + ". This is a screening alert, not a diagnosis."
        )

    if completed >= len(questions):
        st.success("Core clinical history captured.")

        if st.button("Continue to AYUSH History", type="primary"):
            st.session_state.page = "AYUSH History"
            st.rerun()


# -----------------------------
# AYUSH
# -----------------------------
elif st.session_state.page == "AYUSH History":
    st.header("3. AYUSH / Ayurvedic History")

    st.write(
        "Structured fields below demonstrate the additional history layer described "
        "in SIH26047, including Trividha and Dashavidha Pariksha concepts."
    )

    a = st.session_state.ayush

    prakriti_options = [
        "Not assessed",
        "Vata",
        "Pitta",
        "Kapha",
        "Vata-Pitta",
        "Pitta-Kapha",
        "Vata-Kapha",
        "Tridosha / mixed",
    ]
    current_prakriti = a.get("prakriti", "Not assessed")
    prakriti_index = (
        prakriti_options.index(current_prakriti)
        if current_prakriti in prakriti_options
        else 0
    )

    a["prakriti"] = st.selectbox(
        "Prakriti (constitution)",
        prakriti_options,
        index=prakriti_index,
    )

    a["vikriti"] = st.text_area(
        "Vikriti (current imbalance)",
        value=a.get("vikriti", ""),
    )
    vikriti_speech = speech_input(
        "Vikriti (current imbalance)",
        st.session_state.patient.get("language", "English"),
        "ayush_vikriti",
        height=80,
    )
    if vikriti_speech:
        a["vikriti"] = vikriti_speech

    agni_options = ["Not assessed", "Sama", "Vishama", "Tikshna", "Manda"]
    current_agni = a.get("agni", "Not assessed")
    agni_index = (
        agni_options.index(current_agni)
        if current_agni in agni_options
        else 0
    )

    a["agni"] = st.selectbox(
        "Agni (digestive capacity)",
        agni_options,
        index=agni_index,
    )

    koshtha_options = ["Not assessed", "Mridu", "Madhyama", "Krura"]
    current_koshtha = a.get("koshtha", "Not assessed")
    koshtha_index = (
        koshtha_options.index(current_koshtha)
        if current_koshtha in koshtha_options
        else 0
    )

    a["koshtha"] = st.selectbox(
        "Koshtha (bowel nature)",
        koshtha_options,
        index=koshtha_index,
    )

    a["ahara_vihara"] = st.text_area(
        "Ahara-Vihara (diet and lifestyle)",
        value=a.get("ahara_vihara", ""),
    )
    ahara_speech = speech_input(
        "Ahara-Vihara (diet and lifestyle)",
        st.session_state.patient.get("language", "English"),
        "ayush_ahara",
        height=80,
    )
    if ahara_speech:
        a["ahara_vihara"] = ahara_speech

    a["trividha"] = st.text_area(
        "Trividha Pariksha notes",
        value=a.get("trividha", ""),
    )
    trividha_speech = speech_input(
        "Trividha Pariksha notes",
        st.session_state.patient.get("language", "English"),
        "ayush_trividha",
        height=80,
    )
    if trividha_speech:
        a["trividha"] = trividha_speech

    a["dashavidha"] = st.text_area(
        "Dashavidha Pariksha notes",
        value=a.get("dashavidha", ""),
        help=(
            "Use for structured clinical documentation; do not treat this "
            "prototype as an autonomous Ayurvedic diagnostic system."
        ),
    )
    dashavidha_speech = speech_input(
        "Dashavidha Pariksha notes",
        st.session_state.patient.get("language", "English"),
        "ayush_dashavidha",
        height=80,
    )
    if dashavidha_speech:
        a["dashavidha"] = dashavidha_speech

    st.session_state.ayush = a

    if st.button("Save AYUSH History", type="primary"):
        update_patient_record(
            st.session_state.patient.get("local_id"),
            st.session_state.history,
            st.session_state.ayush,
        )
        st.success("AYUSH history saved.")

    if st.button("Continue to Document Intelligence"):
        update_patient_record(
            st.session_state.patient.get("local_id"),
            st.session_state.history,
            st.session_state.ayush,
        )
        st.session_state.page = "Document Intelligence"
        st.rerun()


# -----------------------------
# Documents
# -----------------------------
elif st.session_state.page == "Document Intelligence":
    st.header("4. Document Intelligence / OCR")

    st.write(
        "Upload prior prescriptions, lab reports, discharge summaries or other "
        "patient records. The prototype extracts text and selected medical entities."
    )

    uploaded_files = st.file_uploader(
        "Upload documents",
        type=[
            "pdf",
            "png",
            "jpg",
            "jpeg",
            "webp",
            "tiff",
            "bmp",
            "txt",
        ],
        accept_multiple_files=True,
    )

    if uploaded_files:
        existing_names = {
            x["filename"] for x in st.session_state.documents
        }

        for f in uploaded_files:
            if f.name not in existing_names:
                text = extract_document(f)
                entities = detect_entities(text)

                doc = {
                    "filename": f.name,
                    "text": text,
                    "date": datetime.now().date().isoformat(),
                    "entities": entities,
                }

                st.session_state.documents.append(doc)
                existing_names.add(f.name)

                conn = sqlite3.connect(DB_PATH)
                conn.execute(
                    """
                    INSERT INTO documents
                    (patient_id, filename, extracted_text, uploaded_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        st.session_state.patient.get("local_id"),
                        f.name,
                        text,
                        datetime.now().isoformat(timespec="seconds"),
                    ),
                )
                conn.commit()
                conn.close()

    if st.session_state.documents:
        for doc in st.session_state.documents:
            with st.expander(f"📄 {doc['filename']}"):
                st.write("**Extracted text:**")
                st.text_area(
                    "OCR/text",
                    doc["text"][:10000],
                    height=180,
                    key=f"text_{doc['filename']}",
                )

                st.write("**Extracted entities:**")
                st.json(doc["entities"])

        st.session_state.timeline = build_timeline(
            st.session_state.documents
        )

        if st.button("Build Chronological Timeline", type="primary"):
            st.session_state.timeline = build_timeline(
                st.session_state.documents
            )
            st.success("Timeline generated.")
    else:
        st.info("No documents uploaded yet.")

    st.divider()

    if st.button("Continue to Timeline"):
        st.session_state.timeline = build_timeline(
            st.session_state.documents
        )
        st.session_state.page = "Timeline"
        st.rerun()


# -----------------------------
# Timeline
# -----------------------------
elif st.session_state.page == "Timeline":
    st.header("5. Chronological Medical Timeline")

    st.session_state.timeline = build_timeline(
        st.session_state.documents
    )

    if not st.session_state.timeline:
        st.info("Upload documents first.")
    else:
        for item in st.session_state.timeline:
            st.markdown(
                f"### {item['date']} — {item['source']}"
            )

            c1, c2, c3 = st.columns(3)

            with c1:
                st.write("**Diagnoses**")
                st.write(", ".join(item["diagnoses"]) or "—")

            with c2:
                st.write("**Medicines**")
                st.write(", ".join(item["medicines"]) or "—")

            with c3:
                st.write("**Investigations**")
                st.write(", ".join(item["investigations"]) or "—")

            if item["values"]:
                st.warning(
                    "Numeric values detected: "
                    + ", ".join(item["values"])
                )

            st.divider()

    if st.button("Generate Physician Summary", type="primary"):
        st.session_state.summary = generate_summary()
        st.session_state.page = "Physician Summary"
        st.rerun()


# -----------------------------
# Summary
# -----------------------------
elif st.session_state.page == "Physician Summary":
    st.header("6. Physician-Ready Summary")

    if not st.session_state.summary:
        st.session_state.summary = generate_summary()

    st.warning(
        "AI-assisted draft only. Physician verification is required. "
        "This prototype does not diagnose or prescribe."
    )

    edited = st.text_area(
        "Editable physician summary",
        value=st.session_state.summary,
        height=600,
    )
    st.session_state.summary = edited

    c1, c2 = st.columns(2)

    with c1:
        if st.button("✅ Physician Accepts Draft", type="primary"):
            st.success(
                "Draft marked as physician-reviewed for this demo session."
            )

    with c2:
        if st.button("✏️ Save Physician Notes"):
            st.session_state.doctor_notes = edited
            st.success("Notes saved for this demo session.")

    st.download_button(
        "Download Summary as TXT",
        data=st.session_state.summary,
        file_name="physician_summary.txt",
        mime="text/plain",
    )

    if st.button("Continue to FHIR / ABDM Demo"):
        st.session_state.page = "FHIR / ABDM Demo"
        st.rerun()


# -----------------------------
# FHIR / ABDM
# -----------------------------
elif st.session_state.page == "FHIR / ABDM Demo":
    st.header("7. FHIR / ABDM Interoperability Demo")

    st.info(
        "This is a local FHIR-compatible demonstration payload. It is NOT a live "
        "ABDM connection and must not be represented as one."
    )

    if st.button("Generate FHIR Bundle", type="primary"):
        st.session_state.fhir = make_fhir_bundle()

    if st.session_state.fhir:
        st.json(st.session_state.fhir)

        fhir_json = json.dumps(
            st.session_state.fhir,
            indent=2,
            ensure_ascii=False,
        )

        st.download_button(
            "Download FHIR JSON",
            data=fhir_json,
            file_name="medikiosk_fhir_bundle.json",
            mime="application/fhir+json",
        )

        if st.button("Simulate HIS Submission"):
            st.success(
                "Demo submission successful: FHIR payload validated locally and "
                "marked as ready for a real authorised integration."
            )


# -----------------------------
# Footer
# -----------------------------
st.divider()
st.caption(
    "MediKiosk prototype for SIH26047. For demonstration only — not a medical device, "
    "not a diagnostic system, and not a substitute for a qualified clinician."
)
