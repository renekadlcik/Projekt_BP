import os
import subprocess
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, render_template
import json

import magenta
from magenta.models.melody_rnn import melody_rnn_sequence_generator
from magenta.models.shared import sequence_generator_bundle
from note_seq import midi_io
from note_seq.protobuf import music_pb2
from note_seq.protobuf import generator_pb2

import midi2audio
from midi2audio import FluidSynth as Synth
import re

app = Flask(__name__)

OUTPUT_DIR = "generated_music_files"
os.makedirs(OUTPUT_DIR, exist_ok=True)

HISTORY_FILE = "history.json"

BUNDLE_PATHS = {
    "basic_rnn": "bundles/basic_rnn.mag",
    "attention_rnn": "bundles/attention_rnn.mag"
}

# Upravit cestu k SoundFontu - ZKONTROLUJTE TUTO CESTU!
soundfont_path = r"C:\Users\renek\Downloads\GeneralUser_GS_v2.0.2--doc_r4\GeneralUser-GS\GeneralUser-GS.sf2"
fluidsynth_executable_path = r"C:\Users\renek\Downloads\fluidsynth-2.3.3-win10-x64\bin\fluidsynth.exe"

INSTRUMENT_MIDI_MAP = {
    "piano": 0, "acoustic piano": 0, "grand piano": 0,
    "electric piano": 4, "epiano": 4,
    "organ": 19, "church organ": 19,
    "guitar": 24, "acoustic guitar": 24,
    "electric guitar": 27, "clean electric guitar": 27,
    "distortion guitar": 29, "distorted guitar": 29,
    "overdrive guitar": 30,
    "bass": 33, "finger bass": 33, "acoustic bass": 32, "slap bass": 36,
    "violin": 40, "viola": 41,
    "cello": 42,
    "contrabass": 43,
    "strings": 48, "string ensemble": 48, "orchestra strings": 48, "slow strings": 49, "synth strings": 50,
    "trumpet": 56, "trombone": 57, "tuba": 58, "french horn": 60,
    "saxophone": 66, "alto sax": 66, "tenor sax": 67,
    "flute": 73, "piccolo": 72, "oboe": 68, "clarinet": 71,
    "synth pad": 88, "new age pad": 88, "warm pad": 89, "polysynth pad": 90,
    "choir": 52, "voice aahs": 52,
    "drums": 128
}

REVERSE_INSTRUMENT_MIDI_MAP = {v: k.replace("_", " ").title() for k, v in INSTRUMENT_MIDI_MAP.items()}
REVERSE_INSTRUMENT_MIDI_MAP[128] = "Drums"

GENRE_MAP = {
    "rock": {
        "tempo_range": (120, 180),
        "melody_instrument": 29,
        "bass_instrument": 34,
        "chord_instrument": 30,
        "pad_instrument": None,
        "chords_preset": "rock",
        "drums_preset": "rock"
    },
    "pop": {
        "tempo_range": (100, 140),
        "melody_instrument": 0,
        "bass_instrument": 33,
        "chord_instrument": 27,
        "pad_instrument": 88,
        "chords_preset": "pop",
        "drums_preset": "pop"
    },
    "jazz": {
        "tempo_range": (80, 120),
        "melody_instrument": 26,
        "bass_instrument": 32,
        "chord_instrument": 0,
        "pad_instrument": 48,
        "chords_preset": "jazz",
        "drums_preset": "jazz"
    },
    "classical": {
        "tempo_range": (60, 100),
        "melody_instrument": 40,
        "bass_instrument": 43,
        "chord_instrument": 48,
        "pad_instrument": None,
        "chords_preset": "classical",
        "drums_preset": "none"
    },
    "electronic": {
        "tempo_range": (110, 160),
        "melody_instrument": 80,
        "bass_instrument": 38,
        "chord_instrument": 90,
        "pad_instrument": 91,
        "chords_preset": "electronic",
        "drums_preset": "electronic"
    },
    "happy": {
        "mood_major": True,
        "temperature_range": (0.8, 1.2)
    },
    "sad": {
        "mood_minor": True,
        "temperature_range": (0.5, 0.9)
    },
    "lead synth": {"melody_instrument_override": 80},
    "bass synth": {"bass_instrument_override": 38},
    "pad synth": {"pad_instrument_override": 90},
    "strings": {"pad_instrument_override": 48},
    "choir": {"pad_instrument_override": 52},
    "arpeggio": {"add_arpeggio": True},
    "solo": {"solo_mode": True},
}

def save_history(record):
    history = []
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                history = json.load(f)
        except json.JSONDecodeError:
            pass
    history.insert(0, record)
    history = history[:50]
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, indent=4, ensure_ascii=False)

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return []
    return []

@app.route("/delete_record/<timestamp>", methods=["POST"])
def delete_record(timestamp):
    history = []
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                history = json.load(f)
        except json.JSONDecodeError:
            pass # Soubor je prázdný nebo poškozený, začneme s prázdnou historií

    # Filtrujeme záznamy: ponecháme jen ty, které nemají stejné časové razítko
    # jako záznam, který chceme smazat.
    # Ujistěte se, že timestamp v URL a v JSON souboru jsou ve stejném formátu.
    updated_history = [record for record in history if record.get("timestamp") != timestamp]

    try:
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(updated_history, f, indent=4, ensure_ascii=False)
        return jsonify({"message": "Záznam byl úspěšně smazán."}), 200
    except Exception as e:
        return jsonify({"error": f"Chyba při ukládání historie po smazání: {str(e)}"}), 500

@app.template_filter("datetimeformat")
def datetimeformat(value, input_fmt="%Y%m%d_%H%M%S", output_fmt="%d.%m.%Y %H:%M:%S"):
    try:
        dt = datetime.strptime(value, input_fmt)
        return dt.strftime(output_fmt)
    except ValueError:
        return value

@app.route("/clear_history", methods=["POST"])
def clear_history():
    try:
        if os.path.exists(HISTORY_FILE):
            os.remove(HISTORY_FILE)
        return jsonify({"message": "Celá historie byla úspěšně smazána."}), 200
    except Exception as e:
        return jsonify({"error": f"Chyba při mazání souboru historie: {str(e)}"}), 500

def parse_prompt(prompt, current_params):
    prompt_lower = prompt.lower()

    parsed_params = {
        "length": current_params.get("length", 30),
        "tempo": current_params.get("tempo", 120),
        "temperature": current_params.get("temperature", 1.0),
        "melody_instrument": current_params.get("instrument", 0),
        "bass_instrument": 33,
        "chord_instrument": 29,
        "pad_instrument": None,
        "add_drums": True,
        "chord_progression_type": "standard",
        "major_key": True,
        "add_arpeggio": False,
        "model": current_params.get("model", "basic_rnn")
    }

    # Přednastavení modelu z promptu
    if "attention rnn" in prompt_lower:
        parsed_params["model"] = "attention_rnn"
    elif "basic rnn" in prompt_lower:
        parsed_params["model"] = "basic_rnn"


    tempo_match = re.search(r'(\d+)\s*(bpm|tempo)', prompt_lower)
    if tempo_match:
        parsed_params["tempo"] = int(tempo_match.group(1))
    else:
        for keyword, config in GENRE_MAP.items():
            if keyword in prompt_lower and "tempo_range" in config:
                parsed_params["tempo"] = (config["tempo_range"][0] + config["tempo_range"][1]) // 2
                break
        if "fast" in prompt_lower:
            parsed_params["tempo"] = 160
        elif "slow" in prompt_lower:
            parsed_params["tempo"] = 80
        elif "medium" in prompt_lower:
            parsed_params["tempo"] = 120

    length_match = re.search(r'(\d+)\s*(seconds|s|second)', prompt_lower)
    if length_match:
        parsed_params["length"] = int(length_match.group(1))

    temp_match = re.search(r'temperature\s*[:=]?\s*(\d+\.?\d*)', prompt_lower)
    if temp_match:
        parsed_params["temperature"] = float(temp_match.group(1))
    else:
        for keyword, config in GENRE_MAP.items():
            if keyword in prompt_lower and "temperature_range" in config:
                parsed_params["temperature"] = (config["temperature_range"][0] + config["temperature_range"][1]) / 2
                break
        if "complex" in prompt_lower or "experimental" in prompt_lower:
            parsed_params["temperature"] = max(parsed_params["temperature"], 1.2)
        elif "simple" in prompt_lower or "calm" in prompt_lower:
            parsed_params["temperature"] = min(parsed_params["temperature"], 0.8)

    melody_instrument_found_in_prompt = False
    # Check for specific_instrument by MIDI number first
    inst_num_match = re.search(r'(?:instrument|midi)\s*(\d+)', prompt_lower)
    if inst_num_match:
        parsed_params["melody_instrument"] = int(inst_num_match.group(1))
        melody_instrument_found_in_prompt = True
    else:
        # Then check by name
        for inst_name, midi_num in INSTRUMENT_MIDI_MAP.items():
            if inst_name in prompt_lower:
                if "melody" in prompt_lower or "lead" in prompt_lower or (prompt_lower.startswith(inst_name) and "chords" not in prompt_lower and "bass" not in prompt_lower and "pad" not in prompt_lower):
                    parsed_params["melody_instrument"] = midi_num
                    melody_instrument_found_in_prompt = True
                    break

    if not melody_instrument_found_in_prompt:
        for keyword, config in GENRE_MAP.items():
            if keyword in prompt_lower and "melody_instrument" in config:
                parsed_params["melody_instrument"] = config["melody_instrument"]
                break

    for keyword, config in GENRE_MAP.items():
        if keyword in prompt_lower and "bass_instrument" in config:
            parsed_params["bass_instrument"] = config["bass_instrument"]
            break
    if "bass" in prompt_lower:
        for inst_name, midi_num in INSTRUMENT_MIDI_MAP.items():
            if f"{inst_name} bass" in prompt_lower or f"bass {inst_name}" in prompt_lower:
                parsed_params["bass_instrument"] = midi_num
                break
        else:
            if "acoustic bass" in prompt_lower: parsed_params["bass_instrument"] = 32
            elif "electric bass" in prompt_lower: parsed_params["bass_instrument"] = 33
            elif "synth bass" in prompt_lower: parsed_params["bass_instrument"] = 38

    for keyword, config in GENRE_MAP.items():
        if keyword in prompt_lower and "chord_instrument" in config:
            parsed_params["chord_instrument"] = config["chord_instrument"]
            break
    if "chords" in prompt_lower:
        for inst_name, midi_num in INSTRUMENT_MIDI_MAP.items():
            if f"{inst_name} chords" in prompt_lower:
                parsed_params["chord_instrument"] = midi_num
                break
        else:
            if "piano chords" in prompt_lower: parsed_params["chord_instrument"] = 0
            elif "guitar chords" in prompt_lower: parsed_params["chord_instrument"] = 27

    if "no pad" in prompt_lower or "without pad" in prompt_lower:
        parsed_params["pad_instrument"] = None
    else:
        for keyword, config in GENRE_MAP.items():
            if keyword in prompt_lower and "pad_instrument" in config and config["pad_instrument"] is not None:
                parsed_params["pad_instrument"] = config["pad_instrument"]
                break
        if parsed_params["pad_instrument"] is None:
            for inst_name, midi_num in INSTRUMENT_MIDI_MAP.items():
                if f"{inst_name} pad" in prompt_lower or f"pad {inst_name}" in prompt_lower or "strings" in prompt_lower or "choir" in prompt_lower:
                    parsed_params["pad_instrument"] = midi_num
                    break
            else:
                if "pad" in prompt_lower:
                    parsed_params["pad_instrument"] = 88

    if "arpeggio" in prompt_lower:
        parsed_params["add_arpeggio"] = True

    if "no drums" in prompt_lower or "without drums" in prompt_lower:
        parsed_params["add_drums"] = False
    elif "drums" in prompt_lower:
        parsed_params["add_drums"] = True

    for keyword, config in GENRE_MAP.items():
        if keyword in prompt_lower:
            if "mood_major" in config:
                parsed_params["major_key"] = config["mood_major"]
            if "mood_minor" in config:
                parsed_params["major_key"] = not config["mood_minor"]
            if "chords_preset" in config:
                parsed_params["chord_progression_type"] = config["chords_preset"]
            if "drums_preset" in config:
                if config["drums_preset"] == "none":
                    parsed_params["add_drums"] = False

    parsed_params["temperature"] = max(0.1, min(2.0, parsed_params["temperature"]))

    return parsed_params

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/history")
def history():
    records = load_history()
    for record in records:
        record['instrument_name'] = REVERSE_INSTRUMENT_MIDI_MAP.get(record.get('melody_instrument'), f"Unknown ({record.get('melody_instrument')})")
        record['bass_instrument_name'] = REVERSE_INSTRUMENT_MIDI_MAP.get(record.get('bass_instrument'), f"Unknown ({record.get('bass_instrument')})")
        record['chord_instrument_name'] = REVERSE_INSTRUMENT_MIDI_MAP.get(record.get('chord_instrument'), f"Unknown ({record.get('chord_instrument')})")
        record['pad_instrument_name'] = REVERSE_INSTRUMENT_MIDI_MAP.get(record.get('pad_instrument'), "None")
    return render_template("history.html", records=records)

@app.route("/generate_music", methods=["POST"])
def generate_music():
    data = request.json
    if not data:
        return jsonify({"error": "Nebyla poskytnuta žádná data."}), 400

    # Původní hodnoty, které se případně přepíší z promptu
    current_params = {
        "length": 30, "tempo": 120, "temperature": 1.0,
        "model": "basic_rnn", "instrument": 0 # Defaultní hlavní nástroj (piano)
    }
    prompt = data.get("prompt", "")
    parsed_params = parse_prompt(prompt, current_params)

    length = parsed_params["length"]
    tempo = parsed_params["tempo"]
    temperature = parsed_params["temperature"]
    model = parsed_params["model"]
    melody_instrument = parsed_params["melody_instrument"]
    bass_instrument = parsed_params["bass_instrument"]
    chord_instrument = parsed_params["chord_instrument"]
    pad_instrument = parsed_params["pad_instrument"]
    add_drums = parsed_params["add_drums"]
    chord_progression_type = parsed_params["chord_progression_type"]
    major_key = parsed_params["major_key"]
    add_arpeggio = parsed_params["add_arpeggio"]

    bundle_path = BUNDLE_PATHS.get(model)
    if not bundle_path or not os.path.exists(bundle_path):
        return jsonify({"error": f"Model '{model}' nebyl nalezen."}), 400

    try:
        bundle = sequence_generator_bundle.read_bundle_file(bundle_path)
        generator_map = melody_rnn_sequence_generator.get_generator_map()
        melody_rnn = generator_map[model](checkpoint=None, bundle=bundle)
        melody_rnn.initialize()
    except Exception as e:
        return jsonify({"error": f"Chyba při inicializaci modelu Magenta: {str(e)}"}), 500

    input_sequence = music_pb2.NoteSequence()
    input_sequence.notes.add(pitch=60, start_time=0.0, end_time=0.5, velocity=80)
    input_sequence.total_time = 0.5
    input_sequence.tempos.add(qpm=tempo)

    generator_options = generator_pb2.GeneratorOptions()
    generator_options.args["temperature"].float_value = temperature
    generator_options.generate_sections.add(start_time=input_sequence.total_time, end_time=length)
    note_sequence = melody_rnn.generate(input_sequence, generator_options)

    if chord_progression_type == "rock":
        chord_progression = [
            [60, 64, 67],
            [55, 59, 62],
            [57, 60, 64],
            [62, 66, 69]
        ]
    elif chord_progression_type == "jazz":
        chord_progression = [
            [60, 63, 67, 70],
            [58, 62, 65, 69],
            [55, 59, 62, 65],
            [60, 63, 67, 70]
        ]
    elif chord_progression_type == "pop":
        chord_progression = [
            [60, 64, 67],
            [62, 67, 71],
            [57, 60, 64],
            [55, 59, 62]
        ]
    elif major_key:
        chord_progression = [
            [60, 64, 67],
            [62, 67, 71],
            [57, 60, 64],
            [55, 59, 62]
        ]
    else: # Default or minor key
        chord_progression = [
            [60, 63, 67],
            [62, 65, 69],
            [57, 60, 64],
            [55, 58, 62]
        ]

    measure_duration = 2.0
    total_chord_beats = len(chord_progression) * measure_duration
    num_repetitions = int(length / total_chord_beats) + 1

    for rep in range(num_repetitions):
        for i, chord in enumerate(chord_progression):
            start = (rep * total_chord_beats) + (i * measure_duration)
            if start >= length:
                break
            end = start + 1.5
            for pitch in chord:
                chord_note = note_sequence.notes.add()
                chord_note.pitch = pitch
                chord_note.start_time = start
                chord_note.end_time = end
                chord_note.velocity = 70
                chord_note.instrument = 2
                chord_note.program = chord_instrument
                chord_note.is_drum = False
        if start >= length:
            break

    # Basová linka
    for i in range(0, length, 2):
        if i >= length:
            break
        bass_note = note_sequence.notes.add()
        bass_note.pitch = 36
        bass_note.start_time = i
        bass_note.end_time = i + 1.5
        bass_note.velocity = 80
        bass_note.instrument = 1
        bass_note.program = bass_instrument
        bass_note.is_drum = False


    if add_drums:
        for i in range(0, length):
            if i >= length:
                break
            kick = note_sequence.notes.add()
            kick.pitch = 36
            kick.start_time = i
            kick.end_time = i + 0.2
            kick.velocity = 100
            kick.instrument = 9
            kick.is_drum = True

            if (i % measure_duration) == 0:
                snare = note_sequence.notes.add()
                snare.pitch = 38
                snare.start_time = i + 1.0
                snare.end_time = i + 1.2
                snare.velocity = 90
                snare.instrument = 9
                snare.is_drum = True

            hihat = note_sequence.notes.add()
            hihat.pitch = 42
            hihat.start_time = i
            hihat.end_time = i + 0.1
            hihat.velocity = 70
            hihat.instrument = 9
            hihat.is_drum = True

            hihat2 = note_sequence.notes.add()
            hihat2.pitch = 42
            hihat2.start_time = i + 0.5
            hihat2.end_time = i + 0.6
            hihat2.velocity = 70
            hihat2.instrument = 9
            hihat2.is_drum = True

    if pad_instrument is not None:
        for rep in range(num_repetitions):
            for i, chord in enumerate(chord_progression):
                start = (rep * total_chord_beats) + (i * measure_duration)
                if start >= length:
                    break
                end = start + measure_duration
                pad_root_note = note_sequence.notes.add()
                pad_root_note.pitch = chord[0] - 12
                pad_root_note.start_time = start
                pad_root_note.end_time = end
                pad_root_note.velocity = 60
                pad_root_note.instrument = 3
                pad_root_note.program = pad_instrument
                pad_root_note.is_drum = False

                pad_third_note = note_sequence.notes.add()
                pad_third_note.pitch = chord[1] - 12
                pad_third_note.start_time = start
                pad_third_note.end_time = end
                pad_third_note.velocity = 60
                pad_third_note.instrument = 3
                pad_third_note.program = pad_instrument
                pad_third_note.is_drum = False

                pad_fifth_note = note_sequence.notes.add()
                pad_fifth_note.pitch = chord[2] - 12
                pad_fifth_note.start_time = start
                pad_fifth_note.end_time = end
                pad_fifth_note.velocity = 60
                pad_fifth_note.instrument = 3
                pad_fifth_note.program = pad_instrument
                pad_fifth_note.is_drum = False
            if start >= length:
                break

    if add_arpeggio:
        arpeggio_instrument = melody_instrument if melody_instrument != 0 else 80
        arpeggio_velocity = 85
        arpeggio_duration_per_note = 0.25

        for rep in range(num_repetitions):
            for i, chord in enumerate(chord_progression):
                base_time = (rep * total_chord_beats) + (i * measure_duration)
                if base_time >= length:
                    break

                arpeggio_pitches = [chord[0], chord[1], chord[2], chord[0] + 12, chord[2], chord[1]]

                for j, pitch in enumerate(arpeggio_pitches):
                    note_start_time = base_time + (j * arpeggio_duration_per_note)
                    if note_start_time < base_time + measure_duration:
                        arpeggio_note = note_sequence.notes.add()
                        arpeggio_note.pitch = pitch
                        arpeggio_note.start_time = note_start_time
                        arpeggio_note.end_time = arpeggio_note.start_time + arpeggio_duration_per_note * 0.8
                        arpeggio_note.velocity = arpeggio_velocity
                        arpeggio_note.instrument = 4
                        arpeggio_note.program = arpeggio_instrument
                        arpeggio_note.is_drum = False
            if base_time >= length:
                break

    for note in note_sequence.notes:
        if not note.is_drum and note.instrument not in [1, 2, 3, 4, 9]:
            note.instrument = 0
            note.program = melody_instrument

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename_base = f"generated_{model}_{length}s_{tempo}bpm_{temperature}temp_inst{melody_instrument}_{timestamp}"

    # Použijeme relativní cesty pro uložení
    midi_path = os.path.join(OUTPUT_DIR, filename_base + ".mid")
    wav_path = os.path.join(OUTPUT_DIR, filename_base + ".wav")

    midi_io.sequence_proto_to_midi_file(note_sequence, midi_path)

    # --- ZAČÁTEK DŮLEŽITÉ OPRAVY ---
    # Převedeme všechny cesty na absolutní, než je předáme externímu programu
    abs_fluidsynth_path = os.path.abspath(fluidsynth_executable_path)
    abs_soundfont_path = os.path.abspath(soundfont_path)
    abs_midi_path = os.path.abspath(midi_path)
    abs_wav_path = os.path.abspath(wav_path)

    # Převod MIDI na WAV pomocí subprocess a FluidSynth
    try:
        if not os.path.exists(soundfont_path):
            return jsonify({"error": f"SoundFont soubor nebyl nalezen na absolutní cestě: {abs_soundfont_path}"}), 500
        if not os.path.exists(abs_midi_path):
            return jsonify({"error": f"Vstupní MIDI soubor nebyl nalezen na absolutní cestě: {abs_midi_path}"}), 500

        result = subprocess.run([
            abs_fluidsynth_path,  # Používáme absolutní cestu
            "-ni",
            abs_soundfont_path,  # Používáme absolutní cestu
            abs_midi_path,       # Používáme absolutní cestu
            "-F", abs_wav_path,  # Používáme absolutní cestu
            "-r", "44100"
        ], check=True, capture_output=True, text=True, encoding='utf-8')

        if not os.path.exists(abs_wav_path) or os.path.getsize(abs_wav_path) == 0:
            error_message = f"Převod na WAV selhal (soubor je prázdný nebo nebyl vytvořen). Hláška z FluidSynth: {result.stderr}"
            return jsonify({"error": error_message}), 500

    except subprocess.CalledProcessError as e:
        error_output = e.stderr or "FluidSynth neposkytl žádnou chybovou hlášku."
        return jsonify({"error": f"Chyba při převodu MIDI na WAV (kód {e.returncode}): {error_output}"}), 500
    except FileNotFoundError:
        return jsonify({"error": "FluidSynth nebyl nalezen. Zkontrolujte cestu v proměnné 'fluidsynth_executable_path'."}), 500
    # --- KONEC DŮLEŽITÉ OPRAVY ---

    history_record = {
        "timestamp": timestamp,
        "model": model,
        "length": length,
        "tempo": tempo,
        "temperature": temperature,
        "melody_instrument": melody_instrument,
        "bass_instrument": bass_instrument,
        "chord_instrument": chord_instrument,
        "pad_instrument": pad_instrument,
        "add_drums": add_drums,
        "chord_progression_type": chord_progression_type,
        "major_key": major_key,
        "add_arpeggio": add_arpeggio,
        "prompt": prompt,
        "midi_file": f"/download_music/{os.path.basename(midi_path)}",
        "wav_file": f"/download_music/{os.path.basename(wav_path)}"
    }
    save_history(history_record)

    # Po úspěšném vygenerování souborů vracíme jejich názvy
    return jsonify({
        "midi_file": f"/download_music/{os.path.basename(midi_path)}",
        "wav_file": f"/download_music/{os.path.basename(wav_path)}"
    })

@app.route("/download_music/<filename>")
def download_music(filename):
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=True)

if __name__ == "__main__":
    app.run(debug=True, port=5000)