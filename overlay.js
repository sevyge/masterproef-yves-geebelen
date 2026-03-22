'use strict';

const pipButton = document.getElementById('openPiP');
let screenshotBase64 = null;
let video = null;

pipButton.addEventListener('click', async () => {
  try {
    const videoStream = await navigator.mediaDevices.getDisplayMedia({ video: true });
    window.videoStream = videoStream;
    video = document.createElement('video');
    video.srcObject = videoStream;
    video.play();

  } catch (err) {
    alert('Error: ' + err.message);
    return;
  }

  if ('documentPictureInPicture' in window) {
    const pipWindow = await window.documentPictureInPicture.requestWindow({
      width: 300,
      height: 100,
      disallowReturnToOpener: true
    });

    pipButton.disabled = true;
    pipButton.textContent = "Overlay Open";

    const initialRemaining = Number.isFinite(window.timeRemaining) ? Math.max(0, window.timeRemaining) : 900;
    const initialMinutes = Math.floor(initialRemaining / 60);
    const initialSeconds = initialRemaining % 60;
    const initialTimerLabel = `${initialMinutes}:${initialSeconds.toString().padStart(2, '0')}`;

    pipWindow.document.head.innerHTML = `
      <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    `;
    pipWindow.document.body.innerHTML = `
      <style>
        html, body { 
          height: 100%;
          margin: 0;
          display: flex;
          flex-direction: column;
          gap: 5px;
          padding: 5px;
        }
        button {
          flex: 1;
          font-size: 14px;
        }
      </style>
      <button id="sessionButton" class="btn btn-danger">Start onderzoek</button>
      <button id="timerButton" disabled class="btn btn-light fw-bold fs-5">${initialTimerLabel}</button>
    `;



    const sessionButton = pipWindow.document.getElementById('sessionButton');
    const timerButton = pipWindow.document.getElementById('timerButton');
    window.recordButton = sessionButton;
    window.timerButton = timerButton;

    sessionButton.onclick = async () => {
      try {
        if (sessionButton.textContent === 'Toch verderdoen') {
          sessionButton.textContent = 'Start onderzoek';
          if (window.timerButton) {
            const remaining = Number.isFinite(window.timeRemaining) ? Math.max(0, window.timeRemaining) : 0;
            const minutes = Math.floor(remaining / 60);
            const seconds = remaining % 60;
            window.timerButton.textContent = `${minutes}:${seconds.toString().padStart(2, '0')}`;
          }
          return;
        }
        if (window.vadEnabled) {
          await window.disableVoiceActivation(true);
        } else if (window.enableVoiceActivation) {
          await window.enableVoiceActivation();
        }
      } catch (error) {
        alert('Kon onderzoek niet starten: ' + error.message);
      }
    };

    pipWindow.addEventListener('pagehide', () => {
      pipButton.disabled = false;
      pipButton.textContent = "Open Overlay";
      if (window.vadEnabled && window.disableVoiceActivation) {
        void window.disableVoiceActivation();
      }
      if (video && video.srcObject) {
        video.srcObject.getTracks().forEach(track => track.stop());
      }
      window.recordButton = null;
      window.timerButton = null;
      window.screenshotBase64 = null;
    });

  } else {
    alert('Browser not supported');
  }
});

function takeScreenshot(video) {
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');

  canvas.width = video.videoWidth / 2;
  canvas.height = video.videoHeight / 2;

  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
  screenshotBase64 = canvas.toDataURL('image/png');
  return screenshotBase64;
}

window.captureCurrentScreenshot = () => {
  if (!video || video.readyState < 2) {
    return null;
  }
  return takeScreenshot(video);
};

