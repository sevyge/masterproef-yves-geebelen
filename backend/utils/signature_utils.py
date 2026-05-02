import base64

import fitz


def decode_signature_data(signature_data: str) -> bytes:
    """Decode a base64 data URL signature into PNG bytes."""
    if not signature_data.startswith("data:image/png;base64,"):
        raise ValueError("Invalid signature format. Expected PNG data URL.")

    encoded = signature_data.split(",", 1)[1]
    return base64.b64decode(encoded)


def stamp_signature_on_page_two(
    template_path: str,
    signature_png: bytes,
    signed_at_iso: str,
    participant_id: str,
) -> bytes:
    """Stamp signature image and metadata on page 2 of the consent PDF."""
    pdf = fitz.open(template_path)
    try:
        if pdf.page_count < 2:
            raise ValueError("Consent template has no page 2.")

        page = pdf[1]  # page 2 (0-based index)
        page_rect = page.rect

        left = 72
        top = page_rect.height - 190
        sig_rect = fitz.Rect(left, top, left + 220, top + 80)
        page.insert_image(sig_rect, stream=signature_png, keep_proportion=True)  # type: ignore[attr-defined]

        text = (
            f"Participant ID: {participant_id}\n"
            f"Datum: {signed_at_iso}\n"
            "Elektronische handtekening"
        )
        text_rect = fitz.Rect(left + 235, top, page_rect.width - 72, top + 95)
        page.insert_textbox(text_rect, text, fontsize=9)  # type: ignore[attr-defined]

        return pdf.tobytes()
    finally:
        pdf.close()
