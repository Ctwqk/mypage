# frontpart

The static site (plain HTML/CSS/JS, no build step). It can be served by any static file server, or by the Flask app in `../backpart/DeepSeek`, which serves this directory at `/`.

- `index.html`: home
- `projects/`: project gallery (`media/` holds the re-encoded demo videos and their posters)
- `aboutme/resume.html`: CV viewer for `Taiwei_Cui_CV.pdf`
- `publications/`, `contact/`
- `deepseek_/`: chat UI (needs the backend), `chat-render.js` holds the pure helpers that are unit-tested
- `assets/`: shared stylesheet and favicon

All links are relative so the site also works under a sub-path such as GitHub Pages.
