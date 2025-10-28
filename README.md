# Flickr → Miro Board (Grouped Tiles)

Fetch photos from a **Flickr album** and place them on a **Miro board** as neat, grouped tiles (image + overlay banner).

## What it does

* Pulls all photos from a given Flickr **photoset (album)**.
* Places each as a **tile**: image + light banner + text with a **clickable Flickr URL**.
* Lays tiles out in a grid using absolute positions.
* **Groups** each tile’s parts so they move together on the board.
* Chooses sensible image sizes (prefers `url_c`/`url_l`).

## Requirements

* Python 3.8+
* A Flickr API key
* Miro account with a board you can edit
* Python package: `requests`

## Quick start

```bash
# clone & enter your repo
python3 -m venv venv
source venv/bin/activate
pip install requests

# env vars (example)
export FLICKR_API_KEY=your_flickr_key
export FLICKR_USER_ID=12345678@N00
export FLICKR_PHOTOSET_ID=7215772xxxxxxxxx
export MIRO_TOKEN=miro_oauth_access_token_with_boards_write
export MIRO_BOARD_ID=uXxxXxxXxx==

python3 flickr_to_miro_grouped_v2_coerced.py
```

Or put vars in a `.env`/shell profile and source it.

## Configuration (env vars)

| Variable              | Required | Description                                           |
| --------------------- | -------- | ----------------------------------------------------- |
| `FLICKR_API_KEY`      | ✅        | Your Flickr API key.                                  |
| `FLICKR_USER_ID`      | ✅        | Flickr NSID of the album owner (e.g. `12345678@N00`). |
| `FLICKR_PHOTOSET_ID`  | ✅        | Flickr album (photoset) ID.                           |
| `MIRO_TOKEN`          | ✅        | Miro OAuth token with **`boards:write`**.             |
| `MIRO_BOARD_ID`       | ✅        | Target Miro board ID (from the board URL).            |
| `IMAGES_PER_ROW`      |          | Grid columns (default `6`).                           |
| `CELL_W` / `CELL_H`   |          | Tile width/height in px (default `440` / `420`).      |
| `START_X` / `START_Y` |          | Top-left grid origin (default `0` / `0`).             |
| `OVERLAY_HEIGHT`      |          | Banner height (default `60`).                         |
| `OVERLAY_MARGIN`      |          | Gap below image (default `8`).                        |
| `OVERLAY_COLOR`       |          | Banner fill (default `#FFFFFF`).                      |
| `TEXT_SIZE`           |          | Text size (default `18`).                             |
| `TEXT_PADDING_X`      |          | Horizontal text padding (default `8`).                |

## How layout works

* Items are placed at absolute coordinates in a grid:

  * Column = `(index % IMAGES_PER_ROW)`, Row = `index // IMAGES_PER_ROW`
  * Position = `START_X + col*CELL_W`, `START_Y + row*CELL_H`
* Image is nudged slightly upward to make room for the banner.
* Banner + text sit near the bottom of the tile.
* The three items are **grouped** (via Miro API) so they move as one.

## Notes & tips

* **Flickr privacy**: Only public photos/URLs are fetched. Private albums will return no URLs.
* **Miro scopes**: Token must include **`boards:write`**.
* **Multiple albums**: Run the script again with a different `FLICKR_PHOTOSET_ID`. To avoid overlap, adjust `START_Y` (e.g. add a few thousand px) or change `START_X`.
* **Image sizes**: The script prefers `url_c` (≈800px), then `url_l` (≈1024px), then `url_z`/`url_m`.

## Troubleshooting

* **`400 Invalid parameters` (grouping)**: This version tries multiple payload shapes; if grouping still fails, tiles still get created—just not grouped. You can move them together with shift-select.
* **Nothing appears**: Check the board ID and token scope; verify album is public and ID is correct.
* **Mac “externally-managed-environment”**: Use a virtualenv (`python3 -m venv venv && source venv/bin/activate`) then `pip install requests`.

## Minimal `requirements.txt`

```
requests
```

## License

MIT (or your preference).
