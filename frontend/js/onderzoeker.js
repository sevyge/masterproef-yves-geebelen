document.addEventListener("DOMContentLoaded", function() {
    loadParticipants();
});

async function loadParticipants() {
    const select = document.getElementById("participantSelect");
    if (!select) return;

    try {
        const response = await fetch(`${backendUrl()}/researcher/participants`);
        if (!response.ok) {
            console.error("Failed to fetch participants list");
            return;
        }

        const participants = await response.json();
        
        select.innerHTML = '<option value="">Selecteer...</option>';
        for (let i = 0; i < participants.length; i++) {
            const participantId = participants[i];
            const option = document.createElement("option");
            option.value = participantId;
            option.textContent = `Participant ${participantId}`;
            select.appendChild(option);
        }
    } catch (error) {
        console.error("Error loading participants:", error);
    }
}
