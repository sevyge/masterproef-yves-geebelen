import csv
import glob
import os
import re
import statistics
from collections import Counter
from datetime import datetime

from services.storage_service import get_results_dir

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
EXCLUDED_FOLDERS = {"Testing_example"}

# Effectief gebruikte tool tijdens de sessie (afgelezen uit schermopname)
TOOL_USED = {"1": "Disco", "2": "Disco", "3": "Disco", "4": "bupaR",
             "6": "PM4Py", "7": "Disco", "8": "bupaR"}


def read_csv(path, delimiter=","):
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter=delimiter))


def format_duration(seconds):
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


def read_session(folder):
    transcripts = [p for p in glob.glob(os.path.join(folder, "transcript_*.csv")) if "_original" not in p]
    if not transcripts:
        return None

    rows = read_csv(transcripts[0], delimiter=";")
    speech = [row["transcript"].strip() for row in rows if not row["transcript"].strip().startswith("**")]
    duration = datetime.strptime(rows[-1]["eindtijd"], TIME_FORMAT) - datetime.strptime(
        rows[0]["starttijd"], TIME_FORMAT
    )

    return {
        "segments": len(speech),
        "silences": len(rows) - len(speech),
        "words": sum(len(re.findall(r"[\w']+", text)) for text in speech),
        "seconds": duration.total_seconds(),
        "questionnaire": read_csv(glob.glob(os.path.join(folder, "vragenlijst_*.csv"))[0])[0],
    }


def report(results_dir):
    sessions, dropouts = {}, []
    for participant_id in sorted(os.listdir(results_dir)):
        folder = os.path.join(results_dir, participant_id)
        if not os.path.isdir(folder) or participant_id in EXCLUDED_FOLDERS:
            continue
        session = read_session(folder)
        if session:
            sessions[participant_id] = session
        else:
            dropouts.append(participant_id)

    print(f"Aanmeldingen: {len(sessions) + len(dropouts)} | bruikbaar: {len(sessions)} | "
          f"uitval: {len(dropouts)} ({', '.join(dropouts)})\n")

    print(f"{'ID':>3} {'segmenten':>10} {'stiltes':>8} {'duur':>8} {'w/segment':>10}  gebruikte tool")
    for participant_id, session in sessions.items():
        print(f"{participant_id:>3} {session['segments']:>10} {session['silences']:>8} "
              f"{format_duration(session['seconds']):>8} {session['words'] / session['segments']:>10.1f}  "
              f"{TOOL_USED[participant_id]}")

    seconds = [session["seconds"] for session in sessions.values()]
    segments = [session["segments"] for session in sessions.values()]
    print(f"\nTotaal: {sum(segments)} segmenten, {sum(s['silences'] for s in sessions.values())} stiltes")
    print(f"Sessieduur: {format_duration(min(seconds))}-{format_duration(max(seconds))}, "
          f"mediaan {format_duration(statistics.median(seconds))}, samen {sum(seconds) / 3600:.1f} uur")
    print(f"Segmenten per deelnemer: {min(segments)}-{max(segments)}, mediaan {statistics.median(segments):.0f}\n")

    for participant_id, session in sessions.items():
        answers = session["questionnaire"]
        print(f"{participant_id:>3} | {answers['praktijkervaring']:<16} | eerder EPA: {answers['eerder_epa_project']:<3}"
              f" | {answers['huidige_rol']} | {answers['gebruikte_tools']}")
    print()

    for field, label in [("huidige_rol", "Rol"),
                         ("praktijkervaring", "Ervaring")]:
        counts = Counter(session["questionnaire"][field] for session in sessions.values())
        print(f"{label}: " + ", ".join(f"{count}x {value}" for value, count in counts.most_common()))

    tools_ever_used = Counter(tool.strip() for session in sessions.values()
                              for tool in session["questionnaire"]["gebruikte_tools"].split(","))
    print("Tools ooit gebruikt: " + ", ".join(f"{count}x {tool}" for tool, count in tools_ever_used.most_common()))

    tool_during_session = Counter(TOOL_USED[participant_id] for participant_id in sessions)
    print("Tool tijdens sessie: " + ", ".join(f"{count}x {tool}" for tool, count in tool_during_session.most_common()))


if __name__ == "__main__":
    report(get_results_dir())
