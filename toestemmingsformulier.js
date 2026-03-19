const signatureCanvas = document.getElementById('signatureCanvas');
const signatureCtx = signatureCanvas.getContext('2d');
const clearSignatureBtn = document.getElementById('clearSignatureBtn');
const consentCheck = document.getElementById('consentCheck');
const submitBtn = document.getElementById('submitBtn');

let isDrawing = false;
let hasSignature = false;

function resizeCanvas() {
    const ratio = Math.max(window.devicePixelRatio || 1, 1);
    const rect = signatureCanvas.getBoundingClientRect();

    signatureCanvas.width = Math.floor(rect.width * ratio);
    signatureCanvas.height = Math.floor(rect.height * ratio);
    signatureCtx.setTransform(ratio, 0, 0, ratio, 0, 0);
    signatureCtx.lineWidth = 2;
    signatureCtx.lineCap = 'round';
    signatureCtx.strokeStyle = '#212529';
}

function getRelativePos(event) {
    const rect = signatureCanvas.getBoundingClientRect();
    const point = event.touches ? event.touches[0] : event;
    return {
        x: point.clientX - rect.left,
        y: point.clientY - rect.top
    };
}

function startDrawing(event) {
    event.preventDefault();
    const { x, y } = getRelativePos(event);
    isDrawing = true;
    signatureCtx.beginPath();
    signatureCtx.moveTo(x, y);
}

function draw(event) {
    if (!isDrawing) return;
    event.preventDefault();
    const { x, y } = getRelativePos(event);
    signatureCtx.lineTo(x, y);
    signatureCtx.stroke();
    hasSignature = true;
    validateForm();
}

function stopDrawing(event) {
    if (event) event.preventDefault();
    isDrawing = false;
    signatureCtx.closePath();
}

function clearSignature() {
    signatureCtx.clearRect(0, 0, signatureCanvas.width, signatureCanvas.height);
    hasSignature = false;
    validateForm();
}

function validateForm() {
    const consentOk = consentCheck.checked;
    submitBtn.disabled = !(consentOk && hasSignature);
}

signatureCanvas.addEventListener('mousedown', startDrawing);
signatureCanvas.addEventListener('mousemove', draw);
signatureCanvas.addEventListener('mouseup', stopDrawing);
signatureCanvas.addEventListener('mouseleave', stopDrawing);
signatureCanvas.addEventListener('touchstart', startDrawing, { passive: false });
signatureCanvas.addEventListener('touchmove', draw, { passive: false });
signatureCanvas.addEventListener('touchend', stopDrawing, { passive: false });
clearSignatureBtn.addEventListener('click', clearSignature);
consentCheck.addEventListener('change', validateForm);

window.addEventListener('resize', () => {
    const oldData = hasSignature ? signatureCanvas.toDataURL('image/png') : null;
    resizeCanvas();

    if (oldData) {
        const img = new Image();
        img.onload = function () {
            signatureCtx.drawImage(img, 0, 0, signatureCanvas.clientWidth, signatureCanvas.clientHeight);
        };
        img.src = oldData;
    }
});

resizeCanvas();
validateForm();

document.getElementById('consentForm').addEventListener('submit', async function (e) {
    e.preventDefault();

    const submitSpinner = document.getElementById('submitSpinner');
    const submitText = document.getElementById('submitText');

    if (!hasSignature) {
        alert('Gelieve eerst te ondertekenen in het handtekeningvak.');
        return;
    }

    const payload = new FormData();
    payload.append('signature_data', signatureCanvas.toDataURL('image/png'));

    // Show loading state
    submitBtn.disabled = true;
    submitSpinner.classList.remove('d-none');
    submitText.textContent = 'Even geduld...';

    try {
        const response = await fetch(`${backendUrl()}/consent`, {
            method: 'POST',
            body: payload
        });

        if (response.ok) {
            const data = await response.json();
            localStorage.setItem('participant_id', data.participant_id);
            window.location.href = 'startpagina.html';
        } else {
            alert('Er is een fout opgetreden. Probeer het later opnieuw.');
            submitBtn.disabled = false;
            submitSpinner.classList.add('d-none');
            submitText.textContent = 'Ik ga akkoord en ga verder';
        }
    } catch (error) {
        alert('Kan geen verbinding maken met de server.');
        submitBtn.disabled = false;
        submitSpinner.classList.add('d-none');
        submitText.textContent = 'Ik ga akkoord en ga verder';
    }
});
