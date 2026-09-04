# MediKiosk — SIH26047 Prototype

A local Streamlit prototype for the Smart India Hackathon problem statement
"Patient Case-Taking Software" (SIH26047).

## Demonstrated modules

- Patient identification and consent
- Conversational/adaptive clinical history
- Red-flag screening
- AYUSH/Ayurvedic history layer
- Document upload and OCR/text extraction
- Medical entity extraction
- Chronological timeline
- Physician-editable summary
- FHIR-compatible JSON demonstration
- Local SQLite persistence

## Run

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

Then open the local Streamlit URL shown in the terminal.

## OCR note

Image OCR requires the Tesseract OCR engine to be installed on the machine.
PDFs with embedded text can be read through pypdf. Scanned PDFs may need an
OCR pipeline such as OCRmyPDF/Tesseract in a production implementation.

## Production upgrades

For an SIH submission, the prototype can be upgraded with:

1. Hindi/Indian-language speech-to-text and text-to-speech.
2. A clinical NLP/LLM layer with a strict structured output schema.
3. Human-reviewed red-flag rules validated by clinicians.
4. Proper ABDM/ABHA consent and authorised integration.
5. FHIR R4 profiles/resources aligned with the actual ABDM implementation guide.
6. Secure authentication, encryption, audit logging and role-based access.
7. Better date/entity extraction from prescriptions and lab reports.
8. Real HIS/EHR interoperability.
9. Test datasets and measurable evaluation metrics.

## Safety

The demo deliberately does not make autonomous diagnoses or treatment
recommendations. Red flags are screening alerts for clinician attention, and the
physician summary is explicitly marked as requiring verification.
