'use strict';

const pipButton = document.getElementById('openPiP');
let video = null;

pipButton.addEventListener('click', async () => {
  try {
    const videoStream = await navigator.mediaDevices.getDisplayMedia({ video: true });
    window.videoStream = videoStream;
    video = document.createElement('video');
    video.srcObject = videoStream;
    video.play();

  } catch (err) {
    alert('Schermopname kon niet worden gestart. Controleer of je browser toestemming heeft gegeven.');
    return;
  }

  if ('documentPictureInPicture' in window) {
    const pipWindow = await window.documentPictureInPicture.requestWindow({
      width: 300,
      height: 120,
      disallowReturnToOpener: true
    });
    window.pipWindow = pipWindow;

    pipButton.disabled = true;
    pipButton.textContent = "Overlay Open";


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
        #silencePrompt {
          min-height: 2.5em;
          font-size: 13px;
          line-height: 1.2;
          text-align: center;
          white-space: normal;
        }
        @keyframes pulseAlert {
          0% { background-color: #ffc107; box-shadow: 0 0 0 0 rgba(255, 193, 7, 0.7); border-color: #ffc107; }
          50% { background-color: #fff3cd; box-shadow: 0 0 0 8px rgba(255, 193, 7, 0); border-color: #ffc107; }
          100% { background-color: #ffc107; box-shadow: 0 0 0 0 rgba(255, 193, 7, 0); border-color: #ffc107; }
        }
        .pulsing-alert {
          animation: pulseAlert 1.5s infinite;
          border: 2px solid #ffc107 !important;
        }
      </style>
      <button id="sessionButton" class="btn btn-danger">Start onderzoek</button>
      <div id="silencePrompt" class="alert alert-secondary py-1 px-2 mb-0 d-flex align-items-center justify-content-center text-center"></div>
    `;

    const sessionButton = pipWindow.document.getElementById('sessionButton');
    const silencePrompt = pipWindow.document.getElementById('silencePrompt');
    window.recordButton = sessionButton;
    window.silencePromptElement = silencePrompt;

    sessionButton.onclick = async () => {
      try {
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
      window.silencePromptElement = null;
      window.screenshotBase64 = null;
      window.pipWindow = null;
    });

  } else {
    alert('Browser not supported');
  }
});

function takeScreenshot(video) {
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');

  const maxW = 1280;
  const w = Math.min(video.videoWidth, maxW);
  const h = Math.round((w / video.videoWidth) * video.videoHeight);

  canvas.width = w;
  canvas.height = h;

  ctx.drawImage(video, 0, 0, w, h);
  return canvas.toDataURL('image/jpeg', 0.7);
}

window.captureCurrentScreenshot = () => {
  if (!video || video.readyState < 2) {
    return null;
  }
  return takeScreenshot(video);
};

