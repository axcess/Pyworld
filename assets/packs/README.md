# Full Kenney asset packs (CC0)

The complete packs, unmodified, as downloaded from kenney.nl. They are kept here so any
session or computer can pick new sprites/sounds; the game itself only uses the copies in
`../kenney/`, which `build.py` inlines into `dist/index.html`.

| Zip | Pack | Used for |
|---|---|---|
| `kenney_simple-space.zip` | Simple Space 1.0 (ships, stations, meteors, stars) | map sprites (`PNG/Retina`) |
| `kenney_ui-pack-space-expansion.zip` | UI Pack: Sci-fi 2.0 (panels, buttons, bars, Kenney Future font) | interface (`PNG/*/Double`) and fonts |
| `kenney_sci-fi-sounds.zip` | Sci-Fi Sounds 1.0 (73 .ogg effects) | sound effects |

To use another file: unzip the pack somewhere outside the repo, copy just the file you need
into `../kenney/<space|ui|sounds|fonts>/`, and reference it in the template as
`{{asset:kenney/...}}`. All three are CC0 (see each zip's License.txt); credit to Kenney is
appreciated but not required.
