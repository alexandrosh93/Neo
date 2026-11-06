# News Reel – Κυπριακό Ποδόσφαιρο

Φτιάχνει κάθετο reel (1080x1920, 9:16) με ελληνικό voiceover από το `script.json`.

```bash
pip install pillow edge-tts          # + ffmpeg
apt-get install espeak-ng mbrola mbrola-gr2   # offline εναλλακτική φωνή
python3 build.py script.json reel.mp4
```

- Φωνή: δοκιμάζει πρώτα Microsoft Neural `el-GR-NestorasNeural` (χρειάζεται πρόσβαση στο `speech.platform.bing.com`).
  Αν δεν είναι διαθέσιμη, χρησιμοποιεί offline `espeak-ng` + MBROLA `mb-gr2` (ανδρική).
- Για νέα αγωνιστική: άλλαξε τα `slides` στο `script.json` (τύποι: `intro`, `match`, `table`, `outro`).
  Το `voice` είναι το κείμενο που εκφωνείται και εμφανίζεται ως υπότιτλος.
