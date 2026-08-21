# Kennistypen in exploratieve procesdata-analyse: geautomatiseerde classificatie met Large Language Models

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white" alt="Python 3.12" />
  <img src="https://img.shields.io/badge/FastAPI-0.118-009688?logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/JavaScript-ES6-F7DF1E?logo=javascript&logoColor=black" alt="JavaScript" />
  <img src="https://img.shields.io/badge/HTML5-E34F26?logo=html5&logoColor=white" alt="HTML5" />
  <img src="https://img.shields.io/badge/CSS3-1572B6?logo=css3&logoColor=white" alt="CSS3" />
  <img src="https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white" alt="Docker" />
</p>

Deze repository bevat de volledige broncode van de onderzoeksapplicatie voor de masterproef: "Kennistypen in exploratieve procesdata-analyse: geautomatiseerde classificatie met Large Language Models". De ontwikkelde onderzoeksapplicatie ondersteunt de datacollectie, menselijke- en LLM-coderingen, en de evaluatie in één tool-onafhankelijk geheel.

---

## Abstract

Het domein van exploratieve procesdata-analyse (EPA) heeft zich tot nu toe voornamelijk gericht op het verbeteren van technische tools of op het zichtbare gedrag van de analist. EPA is echter een complex en kennisintensief proces waarbij de expertise en denkwijze van de analist een centrale rol spelen. Om deze cognitieve dimensie meetbaar te maken, worden vier kennistypen geclassificeerd: declaratieve kennis, procedurele kennis, conditionele kennis en domeinkennis. Hoewel deze kennistypen zichtbaar worden via de think-aloud-methode, is het handmatig coderen van de transcripten een arbeidsintensief en subjectief proces. Dit onderzoek introduceert een geautomatiseerde, tool-onafhankelijke methode om deze kennistypen in think-aloud-transcripten te classificeren met behulp van een Large Language Model (LLM) op basis van een deductief codeboek. Om de voorgestelde aanpak te evalueren, werd een studie met zeven deelnemers opgezet waarin de LLM-codering vergeleken werd met een handmatige referentiecodering. Het model vindt 76,0% van de referentiefragmenten terug (recall) tegenover een precisie van 61,9% en een F1-score van 68,2%, en presteert het beste bij domeinkennis en procedurele kennis. Wanneer het LLM een referentiefragment terugvindt, kent het in 92,3% van de gevallen dezelfde code toe. De verschillen liggen dus vooral in welke tekst gecodeerd wordt en hoe die wordt afgebakend, en niet in het toegekende kennistype. Doordat de referentiecodering door één enkele codeur werd opgesteld, ontbreekt een menselijk vergelijkingspunt.

**Keywords:** Exploratieve procesdata-analyse · *Think-aloud* · *Large Language Models* (LLM's) · Kennistypen

---

## Projectstructuur

```text
masterproef-yves-geebelen/
├── app.bat / app.sh           # Start-/stopscript voor de lokale omgeving
├── docker-compose.yml
├── backend/                   # Python FastAPI backend
│   ├── services/
│   │   ├── storage_service.py     # Google Drive-uploads met lokale fallback
│   │   └── transcript_service.py  # Thread-safe transcriptbewerkingen
│   ├── prompts/
│   ├── schemas/
│   ├── utils/
│   ├── Backend.py
│   ├── post_hoc_classification.py
│   ├── evaluate_annotations.py
│   └── dataset_statistics.py
└── frontend/                  # Vanilla HTML5 / CSS3 / ES6 frontend
    ├── assets/
    ├── js/
    ├── pages/
    └── index.html
```

---

## De onderzoeksapplicatie lokaal draaien

Het project gebruikt Docker en Docker Compose voor een consistente, multi-container ontwikkelomgeving.

### Vereisten

* **Docker Desktop** geïnstalleerd en actief op je systeem.

### Opstarten

1. Open een terminal en navigeer naar de hoofdmap van het project:
   ```bash
   cd masterproef-yves-geebelen
   ```
2. Voer het script uit:
   * **Windows:**
     ```cmd
     app.bat
     ```
   * **Linux / macOS:**
     ```bash
     chmod +x app.sh
     ./app.sh
     ```
3. Kies optie `1` in het menu om de containers te bouwen en te starten. Na een paar seconden opent je browser automatisch op `http://localhost`.

### De onderzoeksapplicatie stoppen

Na elke actie verschijnt het menu opnieuw in dezelfde terminal. Kies optie `2` om de containers te stoppen, of optie `4` om ook alle Docker-images en -netwerken op te ruimen (je `.env`-bestand en de data in `results/` blijven behouden).

---

## Omgevingsconfiguratie

Alle variabelen staan toegelicht in `.env.example`. Het opstartscript maakt bij de eerste keer automatisch een `.env` aan en vraagt de AI-sleutels, overige variabelen (Google Drive, researcher-token, ...) vul je zelf aan in `.env` indien nodig.

**Waarschuwing:** `LOCAL_STORAGE_MODE=true` schakelt ook de researcher-token authenticatie op de `/researcher/...`-routes uit (zie `verify_researcher_token` in `backend/Backend.py`). Zet deze nooit op `true` bij een publiek bereikbare deployment.

---

## Dataset analysetaak

> de Leoni, M. (Massimiliano); Mannhardt, Felix (2015): Road Traffic Fine Management Process. Version 1. 4TU.ResearchData. dataset. https://doi.org/10.4121/uuid:270fd440-1057-4fb9-89a9-b699b47990f5

---

## AI-gebruik

In overeenstemming met de universitaire richtlijnen werd het gebruik van generatieve AI transparant bijgehouden, zie [`Bijlage_ Logboek_voor_gebruik_van_AI.pdf`](<Bijlage_ Logboek_voor_gebruik_van_AI.pdf>) voor het volledige logboek met gebruikte tools, prompts en doelstellingen.

---
