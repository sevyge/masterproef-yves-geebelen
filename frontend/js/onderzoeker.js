let currentParticipantId = null;
let segments = [];
let currentSegmentIndex = -1;
let activeSelection = null;
let researcherPassword = "";
let activeScreenshotUrl = null;
let hasUnsavedChanges = false;
let reviewedSegmentIds = new Set();
let hoveredAnnotationIndex = -1;
let hoveredAnnotationSource = "human";

document.addEventListener("DOMContentLoaded", () => {
    setupEventListeners();
    attemptLogin("");
});

function setupEventListeners() {
    document.getElementById("participantSelect").addEventListener("change", handleParticipantChange);
    document.getElementById("saveBtn").addEventListener("click", saveAnnotations);
    document.getElementById("toggleLlmAnnotations").addEventListener("change", () => {
        renderTranscript();
        renderLlmAnnotationsList();
    });
    document.getElementById("transcriptContainer").addEventListener("pointerup", handleTextSelection);
    document.getElementById("classifyBtn").addEventListener("click", runPostHocClassification);
    document.getElementById("evaluateBtn").addEventListener("click", runEvaluation);
    document.getElementById("reviewedToggle").addEventListener("change", handleReviewedToggle);

    // Waarschuw bij verlaten (refresh, tab sluiten, uitloggen) met niet-opgeslagen annotaties.
    window.addEventListener("beforeunload", e => {
        if (hasUnsavedChanges) {
            e.preventDefault();
            e.returnValue = "";
        }
    });

    document.getElementById("selectionPopup").addEventListener("click", e => {
        const btn = e.target.closest(".popup-btn");
        if (btn && activeSelection) addAnnotation(activeSelection.quote, activeSelection.start, activeSelection.end, btn.dataset.label);
        hideSelectionPopup();
    });

    document.addEventListener("pointerdown", e => {
        const popup = document.getElementById("selectionPopup");
        if (popup && !popup.contains(e.target) && !document.getElementById("transcriptContainer").contains(e.target)) {
            hideSelectionPopup();
        }
    });
}

async function attemptLogin(password) {
    if (typeof password !== "string") {
        password = document.getElementById("loginPassword").value;
    }

    const errorEl = document.getElementById("loginError");
    if (errorEl) {
        errorEl.textContent = "";
        errorEl.classList.add("d-none");
    }

    try {
        const response = await fetch(`${backendUrl()}/researcher/participants`, {
            headers: { "X-Researcher-Token": password }
        });

        if (response.ok) {
            researcherPassword = password;
            document.getElementById("loginScreen").classList.add("d-none");
            document.getElementById("mainWorkspace").classList.remove("d-none");

            const participants = await response.json();
            const selectEl = document.getElementById("participantSelect");
            selectEl.innerHTML = participants.map(p => `<option value="${p}">Deelnemer ${p}</option>`).join('');

            if (participants[0]) {
                loadParticipantData(participants[0]);
            }
            return true;
        }

        if (response.status === 429) {
            if (password !== "") {
                try {
                    const errData = await response.json();
                    showLoginError(errData.detail || "Te veel pogingen. Toegang is 15 minuten geblokkeerd.");
                } catch {
                    showLoginError("Te veel pogingen. Toegang is 15 minuten geblokkeerd.");
                }
            }
            return false;
        }

        if (response.status === 401) {
            if (password !== "") showLoginError("Ongeldig wachtwoord!");
            return false;
        }

        showLoginError("Fout bij inloggen.");
        return false;
    } catch (error) {
        console.error("Error logging in:", error);
        if (password !== "") showLoginError("Netwerkfout bij inloggen.");
        return false;
    }
}

function showLoginError(message) {
    const errorEl = document.getElementById("loginError");
    if (errorEl) {
        errorEl.textContent = message;
        errorEl.classList.remove("d-none");
    } else {
        alert(message);
    }
}

window.attemptLogin = attemptLogin;

function handleLogout() {
    if (hasUnsavedChanges &&
        !confirm("Je hebt niet-opgeslagen annotaties. Toch uitloggen zonder op te slaan?")) {
        return;
    }
    hasUnsavedChanges = false;
    window.location.reload();
}
window.handleLogout = handleLogout;

function handleParticipantChange(e) {
    const newValue = e.target.value;
    if (hasUnsavedChanges &&
        !confirm("Je hebt niet-opgeslagen annotaties. Doorgaan zonder op te slaan?")) {
        e.target.value = currentParticipantId || "";
        return;
    }
    if (newValue) {
        loadParticipantData(newValue);
    } else {
        clearWorkspace();
    }
}

async function loadParticipantData(participantId) {
    currentParticipantId = participantId;
    segments = [];
    currentSegmentIndex = -1;
    hasUnsavedChanges = false;
    loadReviewedState(participantId);
    clearWorkspace();

    const spinner = '<div class="text-center py-5"><div class="spinner-border spinner-border-sm text-secondary" role="status"></div></div>';
    document.getElementById("segmentsList").innerHTML = spinner;
    document.getElementById("transcriptContainer").innerHTML = spinner;
    document.getElementById("screenshotViewer").innerHTML = spinner;

    try {
        const response = await fetch(`${backendUrl()}/researcher/participant/${participantId}/transcript`, {
            headers: {
                "X-Researcher-Token": researcherPassword
            }
        });
        if (response.status === 401) return window.location.reload();
        if (!response.ok) {
            console.error("Failed to fetch participant transcript");
            clearWorkspace();
            return;
        }

        segments = await response.json();
        for (let i = 0; i < segments.length; i++) {
            // Normalize newlines to spaces so Range.toString() matches textContent
            segments[i].transcript = (segments[i].transcript || "").replace(/\n/g, " ");
            if (!segments[i].human_annotaties) segments[i].human_annotaties = [];
            if (!segments[i].llm_annotaties) segments[i].llm_annotaties = [];
        }

        renderSegments();

        if (segments.length > 0) {
            selectSegment(0);
        }
    } catch (error) {
        console.error("Error loading participant data:", error);
        clearWorkspace();
    }
}

// "Nagekeken" is puur een lokaal voortgangshulpmiddel voor de onderzoeker
function reviewedStorageKey(participantId) {
    return `onderzoeker_reviewed_${participantId}`;
}

function loadReviewedState(participantId) {
    try {
        const raw = localStorage.getItem(reviewedStorageKey(participantId));
        reviewedSegmentIds = new Set(raw ? JSON.parse(raw) : []);
    } catch {
        reviewedSegmentIds = new Set();
    }
}

function saveReviewedState() {
    if (!currentParticipantId) return;
    localStorage.setItem(reviewedStorageKey(currentParticipantId), JSON.stringify([...reviewedSegmentIds]));
}

function handleReviewedToggle(e) {
    if (currentSegmentIndex < 0) return;
    const segmentId = segments[currentSegmentIndex].segment_id;
    if (e.target.checked) {
        reviewedSegmentIds.add(segmentId);
    } else {
        reviewedSegmentIds.delete(segmentId);
    }
    saveReviewedState();
    renderSegments();
}

function renderReviewedToggle() {
    const toggle = document.getElementById("reviewedToggle");
    if (currentSegmentIndex < 0) {
        toggle.checked = false;
        toggle.disabled = true;
        return;
    }
    toggle.disabled = false;
    toggle.checked = reviewedSegmentIds.has(segments[currentSegmentIndex].segment_id);
}

function renderScreenshotPlaceholder(message) {
    return `
        <span class="text-muted" id="screenshotPlaceholder">
            <i class="bi bi-image fs-1 d-block text-center"></i>${message}
        </span>
    `;
}

function clearWorkspace() {
    hideSelectionPopup();
    if (activeScreenshotUrl) {
        URL.revokeObjectURL(activeScreenshotUrl);
        activeScreenshotUrl = null;
    }
    document.getElementById("segmentsList").innerHTML = "";
    document.getElementById("progressIndicator").textContent = "0 / 0";
    document.getElementById("transcriptContainer").innerHTML = "";
    document.getElementById("screenshotViewer").innerHTML = renderScreenshotPlaceholder("Screenshot context");
    document.getElementById("annotationsList").innerHTML = "";
}

function renderSegments() {
    let html = "";
    for (let i = 0; i < segments.length; i++) {
        const segment = segments[i];
        const isActive = (i === currentSegmentIndex);
        const count = segment.human_annotaties.length;
        const isReviewedEmpty = count === 0 && reviewedSegmentIds.has(segment.segment_id);
        const badgeHtml = count > 0
            ? `<span class="badge ${isActive ? 'bg-light text-dark' : 'bg-secondary text-white'} rounded-circle">${count}</span>`
            : isReviewedEmpty
                ? `<i class="bi bi-check-circle ${isActive ? 'text-white' : 'text-success'}" title="Nagekeken, geen codeerbaar fragment"></i>`
                : `<i class="bi bi-circle ${isActive ? 'text-white-50' : 'text-muted'}"></i>`;

        html += `
            <div class="list-group-item list-group-item-action p-3 ${isActive ? 'active bg-danger border-danger' : ''}" 
                 style="cursor: pointer;" onclick="selectSegment(${i})">
                <div class="d-flex justify-content-between align-items-center mb-1">
                    <span class="fw-bold">Segment ${segment.segment_id}</span>
                    ${badgeHtml}
                </div>
                <small class="d-block text-wrap ${isActive ? '' : 'text-muted'}">${segment.transcript || ""}</small>
            </div>
        `;
    }
    document.getElementById("segmentsList").innerHTML = html;
    updateProgress();
}

function updateProgress() {
    let codedCount = 0;
    for (let i = 0; i < segments.length; i++) {
        const segment = segments[i];
        if (segment.human_annotaties.length > 0 || reviewedSegmentIds.has(segment.segment_id)) {
            codedCount++;
        }
    }
    document.getElementById("progressIndicator").textContent = `${codedCount} / ${segments.length}`;
}

function selectSegment(index) {
    hideSelectionPopup();
    hoveredAnnotationIndex = -1;
    currentSegmentIndex = index;
    renderSegments();
    loadSegmentDetails(index);
}

async function loadSegmentDetails(index) {
    const screenshotViewer = document.getElementById("screenshotViewer");

    if (index < 0 || index >= segments.length) {
        document.getElementById("transcriptContainer").innerHTML = "";
        screenshotViewer.innerHTML = renderScreenshotPlaceholder("Screenshot context");
        return;
    }

    renderTranscript();
    renderAnnotationsList();
    renderReviewedToggle();

    const segment = segments[index];
    if (segment.screenshot_bestandsnaam) {
        const segmentIndexAtRequest = index;
        const spinner = '<div class="text-center py-5"><div class="spinner-border spinner-border-sm text-secondary" role="status"></div></div>';
        screenshotViewer.innerHTML = spinner;

        try {
            const response = await fetch(`${backendUrl()}/researcher/participant/${currentParticipantId}/screenshot/${segment.screenshot_bestandsnaam}`, {
                headers: {
                    "X-Researcher-Token": researcherPassword
                }
            });
            if (response.status === 401) return window.location.reload();
            if (!response.ok) {
                if (currentSegmentIndex === segmentIndexAtRequest) {
                    screenshotViewer.innerHTML = renderScreenshotPlaceholder("Fout bij laden screenshot");
                }
                return;
            }
            const blob = await response.blob();
            if (currentSegmentIndex !== segmentIndexAtRequest) {
                return;
            }
            if (activeScreenshotUrl) {
                URL.revokeObjectURL(activeScreenshotUrl);
            }
            activeScreenshotUrl = URL.createObjectURL(blob);
            screenshotViewer.innerHTML = `<img src="${activeScreenshotUrl}" alt="Screenshot Context" class="img-fluid border rounded" style="max-height: 100%; max-width: 100%; object-fit: contain;">`;
        } catch (error) {
            console.error("Error loading screenshot:", error);
            if (currentSegmentIndex === segmentIndexAtRequest) {
                screenshotViewer.innerHTML = renderScreenshotPlaceholder("Netwerkfout bij laden screenshot");
            }
        }
    } else {
        screenshotViewer.innerHTML = renderScreenshotPlaceholder("Geen screenshot beschikbaar");
    }
}

function getSelectedTextInfo() {
    const selection = window.getSelection();
    if (!selection || selection.rangeCount === 0) return null;

    const range = selection.getRangeAt(0);
    const container = document.getElementById("transcriptContainer");

    if (!container.contains(range.commonAncestorContainer)) return null;

    const fullText = range.toString();
    const trimmedText = fullText.trim();
    if (!trimmedText) return null;

    const preSelectionRange = range.cloneRange();
    preSelectionRange.selectNodeContents(container);
    preSelectionRange.setEnd(range.startContainer, range.startOffset);

    const leadingSpaces = fullText.match(/^\s*/)[0].length;
    const trailingSpaces = fullText.match(/\s*$/)[0].length;

    const start = preSelectionRange.toString().length + leadingSpaces;
    const end = preSelectionRange.toString().length + fullText.length - trailingSpaces;

    return {
        quote: trimmedText,
        start: start,
        end: end
    };
}

function addAnnotation(quote, start, end, label) {
    const segment = segments[currentSegmentIndex];
    segment.human_annotaties.push({
        label: label,
        quote: quote,
        start: start,
        end: end
    });

    hasUnsavedChanges = true;
    window.getSelection().removeAllRanges();
    renderTranscript();
    renderAnnotationsList();
    renderSegments();
}

function handleTextSelection() {
    activeSelection = getSelectedTextInfo();
    const popup = document.getElementById("selectionPopup");
    if (!activeSelection) {
        hideSelectionPopup();
        return;
    }

    const selection = window.getSelection();
    const range = selection.getRangeAt(0);
    const rect = range.getBoundingClientRect();

    popup.classList.remove("d-none");

    const popupWidth = popup.offsetWidth || 230;
    const popupHeight = popup.offsetHeight || 42;

    popup.style.left = `${rect.left + window.scrollX + (rect.width / 2) - (popupWidth / 2)}px`;
    popup.style.top = `${rect.top + window.scrollY - popupHeight - 8}px`;
}

function hideSelectionPopup() {
    activeSelection = null;
    const popup = document.getElementById("selectionPopup");
    if (popup) {
        popup.classList.add("d-none");
    }
}

function deleteAnnotation(idx) {
    if (currentSegmentIndex < 0) return;

    const segment = segments[currentSegmentIndex];
    segment.human_annotaties.splice(idx, 1);

    hoveredAnnotationIndex = -1;
    hasUnsavedChanges = true;
    renderTranscript();
    renderAnnotationsList();
    renderSegments();
}

function getCategoryColor(label) {
    if (label === "DK") return "warning";
    if (label === "PK") return "primary";
    if (label === "CK") return "success";
    if (label === "DOM") return "danger";
    return "secondary";
}

function escapeHtml(txt) {
    return txt
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
}

function sortLongestFirst(annotations) {
    return (annotations || []).slice().sort((a, b) => (b.end - b.start) - (a.end - a.start));
}

function wrapChunk(chunk, humanClass, llmClass) {
    let html = escapeHtml(chunk);
    if (llmClass) html = `<span class="${llmClass}">${html}</span>`;
    if (humanClass) html = `<span class="${humanClass}">${html}</span>`;
    return html;
}

function renderTranscript() {
    const transcriptContainer = document.getElementById("transcriptContainer");
    if (currentSegmentIndex < 0) {
        transcriptContainer.innerHTML = "";
        return;
    }

    const segment = segments[currentSegmentIndex];
    const text = segment.transcript || "";

    const humanClasses = new Array(text.length).fill("");
    const llmClasses = new Array(text.length).fill("");

    const humanBase = new Array(text.length).fill("");
    const humanInner = new Array(text.length).fill("");
    for (const ann of sortLongestFirst(segment.human_annotaties)) {
        const color = getCategoryColor(ann.label);
        for (let j = ann.start; j < ann.end; j++) {
            if (j < 0 || j >= text.length) continue;
            if (humanBase[j]) humanInner[j] = color;
            else humanBase[j] = color;
        }
    }

    const hovered = new Array(text.length).fill(false);
    const hoveredList = hoveredAnnotationSource === "llm" ? segment.llm_annotaties : segment.human_annotaties;
    const hoveredAnn = (hoveredList || [])[hoveredAnnotationIndex];
    if (hoveredAnn) {
        for (let j = hoveredAnn.start; j < hoveredAnn.end; j++) {
            if (j >= 0 && j < text.length) hovered[j] = true;
        }
    }

    for (let j = 0; j < text.length; j++) {
        if (humanBase[j]) {
            humanClasses[j] = `bg-${humanBase[j]}-subtle`;
            if (humanInner[j]) humanClasses[j] += ` border-bottom border-2 border-${humanInner[j]}`;
        }
        if (hovered[j]) humanClasses[j] += " annotation-hover";
    }

    const showLlm = document.getElementById("toggleLlmAnnotations").checked;
    if (showLlm && segment.llm_annotaties) {
        const llmBase = new Array(text.length).fill("");
        const llmOverlap = new Array(text.length).fill(false);
        for (const ann of sortLongestFirst(segment.llm_annotaties)) {
            const color = getCategoryColor(ann.label);
            for (let j = ann.start; j < ann.end; j++) {
                if (j < 0 || j >= text.length) continue;
                if (llmBase[j]) llmOverlap[j] = true;
                else llmBase[j] = color;
            }
        }
        for (let j = 0; j < text.length; j++) {
            if (!llmBase[j]) continue;
            const dikte = llmOverlap[j] ? "border-4" : "border-2";
            llmClasses[j] = `llm-annotation border-bottom ${dikte} border-${llmBase[j]}`;
        }
    }

    let html = "";
    let currentChunk = "";
    let currentHuman = humanClasses[0] || "";
    let currentLlm = llmClasses[0] || "";

    for (let i = 0; i < text.length; i++) {
        if (humanClasses[i] !== currentHuman || llmClasses[i] !== currentLlm) {
            html += wrapChunk(currentChunk, currentHuman, currentLlm);
            currentChunk = "";
            currentHuman = humanClasses[i];
            currentLlm = llmClasses[i];
        }
        currentChunk += text[i];
    }

    if (currentChunk) {
        html += wrapChunk(currentChunk, currentHuman, currentLlm);
    }

    transcriptContainer.innerHTML = html;
}

function renderAnnotationsList() {
    if (currentSegmentIndex < 0) return;

    const segment = segments[currentSegmentIndex];
    const annotations = segment.human_annotaties || [];
    let html = "";

    for (let i = 0; i < annotations.length; i++) {
        const ann = annotations[i];
        const color = getCategoryColor(ann.label);
        const textClass = ann.label === "DK" ? "text-dark" : "text-white";

        html += `
            <div class="card mb-2 border-light shadow-sm"
                 onmouseenter="setHoveredAnnotation(${i})" onmouseleave="setHoveredAnnotation(-1)">
                <div class="card-body p-2 d-flex align-items-center justify-content-between">
                    <div class="d-flex align-items-center gap-2">
                        <span class="badge bg-${color} ${textClass}">${ann.label}</span>
                        <span class="small font-monospace text-truncate" style="max-width: 180px;">"${escapeHtml(ann.quote)}"</span>
                    </div>
                    <button class="btn btn-link text-danger p-0 border-0" onclick="deleteAnnotation(${i})">
                        <i class="bi bi-trash"></i>
                    </button>
                </div>
            </div>
        `;
    }
    document.getElementById("annotationsList").innerHTML = html;
    renderLlmAnnotationsList();
}

function renderLlmAnnotationsList() {
    const segment = segments[currentSegmentIndex];
    const annotations = segment.llm_annotaties || [];
    const showLlm = document.getElementById("toggleLlmAnnotations").checked;
    const section = document.getElementById("llmAnnotationsSection");

    section.classList.toggle("d-none", !showLlm || annotations.length === 0);
    if (!showLlm || annotations.length === 0) return;

    let html = "";
    for (let i = 0; i < annotations.length; i++) {
        const ann = annotations[i];
        const color = getCategoryColor(ann.label);
        const textClass = ann.label === "DK" ? "text-dark" : "text-white";

        html += `
            <div class="card mb-2 bg-light border-light shadow-sm"
                 onmouseenter="setHoveredAnnotation(${i}, 'llm')" onmouseleave="setHoveredAnnotation(-1)">
                <div class="card-body p-2 d-flex align-items-center gap-2">
                    <span class="badge bg-${color} ${textClass}">${ann.label}</span>
                    <span class="small font-monospace text-truncate" style="max-width: 200px;">"${escapeHtml(ann.quote)}"</span>
                </div>
            </div>
        `;
    }
    document.getElementById("llmAnnotationsList").innerHTML = html;
}

function setHoveredAnnotation(index, source = "human") {
    hoveredAnnotationIndex = index;
    hoveredAnnotationSource = source;
    renderTranscript();
}

window.setHoveredAnnotation = setHoveredAnnotation;
window.deleteAnnotation = deleteAnnotation;
window.selectSegment = selectSegment;

async function saveAnnotations() {
    if (!currentParticipantId || segments.length === 0) return;

    const saveBtn = document.getElementById("saveBtn");
    const originalText = saveBtn.innerHTML;
    saveBtn.disabled = true;
    saveBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Opslaan...';

    try {
        const response = await fetch(`${backendUrl()}/researcher/participant/${currentParticipantId}/annotations`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-Researcher-Token": researcherPassword
            },
            body: JSON.stringify(segments)
        });

        if (response.status === 401) return window.location.reload();

        if (response.ok) {
            hasUnsavedChanges = false;
            alert("Annotaties succesvol opgeslagen!");
        } else {
            alert("Fout bij het opslaan van annotaties.");
        }
    } catch (error) {
        console.error("Error saving annotations:", error);
        alert("Netwerkfout bij het opslaan.");
    } finally {
        saveBtn.disabled = false;
        saveBtn.innerHTML = originalText;
    }
}

async function runPostHocClassification() {
    if (!currentParticipantId) return;

    const classifyBtn = document.getElementById("classifyBtn");
    const originalText = classifyBtn.innerHTML;
    classifyBtn.disabled = true;
    classifyBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span> Classificeren...';

    try {
        const response = await fetch(`${backendUrl()}/researcher/participant/${currentParticipantId}/classify_post_hoc`, {
            method: "POST",
            headers: {
                "X-Researcher-Token": researcherPassword
            }
        });

        if (response.status === 401) return window.location.reload();

        if (response.ok) {
            alert("LLM Post-hoc Classificatie succesvol uitgevoerd!");
            await loadParticipantData(currentParticipantId);
        } else {
            const err = await response.json();
            alert("Fout bij uitvoeren classificatie: " + (err.detail || "Onbekende fout"));
        }
    } catch (error) {
        console.error("Error executing post-hoc classification:", error);
        alert("Netwerkfout bij het uitvoeren van de classificatie.");
    } finally {
        classifyBtn.disabled = false;
        classifyBtn.innerHTML = originalText;
    }
}

async function runEvaluation() {
    if (!currentParticipantId) return;

    const evaluateBtn = document.getElementById("evaluateBtn");
    const originalText = evaluateBtn.innerHTML;
    evaluateBtn.disabled = true;
    evaluateBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span> Evalueren...';

    try {
        const response = await fetch(`${backendUrl()}/researcher/participant/${currentParticipantId}/evaluate`, {
            method: "POST",
            headers: {
                "X-Researcher-Token": researcherPassword
            }
        });

        if (response.status === 401) return window.location.reload();

        if (response.ok) {
            const results = await response.json();
            showEvaluationModal(results);
        } else {
            const err = await response.json();
            alert("Fout bij uitvoeren evaluatie: " + (err.detail || "Onbekende fout"));
        }
    } catch (error) {
        console.error("Error executing evaluation:", error);
        alert("Netwerkfout bij het uitvoeren van de evaluatie.");
    } finally {
        evaluateBtn.disabled = false;
        evaluateBtn.innerHTML = originalText;
    }
}

function showEvaluationModal(results) {
    const tableBody = document.getElementById("evaluationTableBody");
    tableBody.innerHTML = ["DOM", "DK", "PK", "CK", "TOTAAL"].map(cat => {
        const res = results[cat];
        if (!res) return "";
        
        const mens = res.true_positives + res.false_negatives;
        const llm = res.true_positives + res.false_positives;
        const isTotal = cat === "TOTAAL" ? "table-secondary fw-bold" : "";
        
        return `
            <tr class="${isTotal}">
                <td class="fw-bold">${cat}</td>
                <td>${mens}</td>
                <td>${llm}</td>
                <td>${res.true_positives}</td>
                <td>${(res.precision * 100).toFixed(2)}%</td>
                <td>${(res.recall * 100).toFixed(2)}%</td>
                <td class="text-primary fw-bold">${(res.f1_score * 100).toFixed(2)}%</td>
            </tr>
        `;
    }).join("");

    new bootstrap.Modal(document.getElementById('evaluationModal')).show();
}
