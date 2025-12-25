'use strict';

const serverStatusElement = document.getElementById('serverStatus');

function setServerStatus(text, color) {
    serverStatusElement.innerHTML = `<span style="color:${color}">● </span>${text}`;
}

async function checkServerStatus() {
    setServerStatus('Connecting to server...', 'orange');
    try {
        const response = await fetch("http://localhost:8000" + '/');
        if (response.ok) {
            setServerStatus('Server status: Online', 'green');
        } else {
            setServerStatus('Server status: Error', 'red');
        }
    } catch (error) {
        setServerStatus('Server status: Offline', 'red');
    }
}

window.addEventListener('load', checkServerStatus);
