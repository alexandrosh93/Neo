# ΠΑΣΑ στα ΝΕΑ – News Reel

Κάθετο reel (1080x1920, 9:16) για τα νέα του κυπριακού ποδοσφαίρου, με ελληνικό voiceover
και υπότιτλους συγχρονισμένους λέξη-λέξη.

```bash
pip install pillow edge-tts     # + ffmpeg
python3 build.py script.json reel.mp4
```

- **Φωνή:** Microsoft Neural `el-GR-NestorasNeural` (ανδρική) μέσω edge-tts — χρειάζεται πρόσβαση στο
  `speech.platform.bing.com`. Αν δεν υπάρχει, πέφτει σε offline espeak-ng/MBROLA (robotic).
  Αλλάζεις φωνή/ταχύτητα με `voice` / `rate` στο `script.json`.
- **Νέα επεισόδια:** άλλαξε τα `stories` στο `script.json`:
  - `tag` – π.χ. `05 / ΕΥΡΩΠΗ`
  - `headline` – 2 γραμμές, ό,τι είναι σε `[αγκύλες]` βγαίνει κίτρινο
  - `body` – το κείμενο στο χαρτί
  - `image` – (προαιρετικά) φωτογραφία, π.χ. `photos/1.jpg`· μπαίνει σε κάδρο με zoom και τότε το `body` δεν εμφανίζεται
  - `voice` – τι εκφωνείται (γράψε αριθμούς/ώρες ολογράφως για σωστή προφορά)
- **Hook:** (προαιρετικό) `hook` στο `script.json` — full-screen φωτογραφία + τεράστιος τίτλος από το 1ο frame, φωνή από 0", πριν το intro. Πεδία: `tag`, `headline`, `image`, `voice`, `size`.
- **Intro:** `start` κόβει τα πρώτα δευτερόλεπτα του clip.
- **Intro (συνέχεια):** `intro.video` (assets/intro.mp4) παίζει πρώτο· η φωνή ξεκινά στο `voice_at` (δευτ.) και η μουσική χαμηλώνει στο `music_volume`.
- Στο τέλος εμφανίζεται recap με όλα τα θέματα (σαν το poster).
- `assets/logo.png` – λογότυπο footer, `assets/fonts/` – Fira Sans Extra Condensed (SIL OFL).

## Προφορά (pronunciations.json)

Λεξικό για το πώς λέει η φωνή συντομογραφίες/ονόματα. Αριστερά όπως γράφεται (έτσι φαίνεται και στους
υπότιτλους), δεξιά όπως εκφωνείται. Εφαρμόζεται αυτόματα σε κάθε reel.

```json
{ "ΓΣΠ": "Γκα Σι Πι" }
```
