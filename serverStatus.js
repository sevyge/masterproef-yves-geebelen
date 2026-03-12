'use strict';

const serverStatusElement = document.getElementById('serverStatus');
let lastStatus = 'unknown';
const backendBaseUrl = backendUrl();

function setServerStatus(text, color) {
    serverStatusElement.innerHTML = `<span style="color:${color}">● </span>${text}`;
}

async function checkServerStatus() {
    if (lastStatus !== "online") {
        setServerStatus('Connecting to server...', 'orange');
    }
    try {
        const response = await fetch(backendBaseUrl + '/');
        if (response.ok) {
            lastStatus = "online";
            setServerStatus('Server status: Online', 'green');
        } else {
            lastStatus = "error";
            setServerStatus('Server status: Error', 'red');
        }
    } catch (error) {
        lastStatus = "offline";
        setServerStatus('Server status: Offline', 'red');
    }
}

window.addEventListener('load', () => {
    checkServerStatus();
    setInterval(checkServerStatus, 10000);
});
