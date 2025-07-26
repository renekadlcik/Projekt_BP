# AI Generátor hudby

Open-source webová aplikace pro generování hudby pomocí umělé inteligence (Magenta + Flask).

## Funkcionalita

- Vygenerování hudební skladby podle zadaných parametrů (žánr, tempo, nástroje, akordy, délka…)
- Volba modelu (Basic_RNN, Attention_RNN, Lookback_RNN)
- Stažení skladby ve formátu MIDI i WAV
- Uložení a prohlížení historie vygenerovaných skladeb
- Přehledné webové rozhraní (HTML/CSS/JS, žádný framework)

## Požadavky

- Python 3.8+
- [Magenta](https://github.com/magenta/magenta)
- Flask
- FluidSynth
- Další viz `requirements.txt`

## Instalace

```bash
git clone https://github.com/TVUJ_GITHUB/Projekt_BP.git
cd Projekt_BP
pip install -r requirements.txt

## Spuštění aplikace
python app.py
Webovou aplikaci otevři v prohlížeči na adrese http://localhost:5000

## Použití
1. Na hlavní stránce vyplň parametry skladby (název, žánr, tempo, délka, model…)
2. Klikni na Generovat hudbu
3. Po vygenerování můžeš stáhnout MIDI nebo WAV, případně si skladbu přehrát přímo v prohlížeči
4. V historii najdeš seznam všech svých skladeb

## Licence
Projekt je licencován pod MIT licencí.

Autor: René Kadlčík
Více info v dokumentaci bakalářské práce.


