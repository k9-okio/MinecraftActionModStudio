# Player Model Animation

Forge 26.3 / Forge 66.0.9 player rig test mod.

The visible vanilla player parts are hidden and replaced by a custom model with:

- two-section torso: `spine` and `chest`
- two-section arms: upper arm and forearm
- two-section legs: thigh and shin
- the supplied `run` animation, driven by Minecraft's movement phase

The player's current skin is used. Base skin, hat, jacket, sleeves and pants are mapped from the standard 64x64 player skin layout.

The vanilla player body is suppressed by canceling its deferred render type. Its
armor/cape/name-tag layers are kept, while the custom body is rendered from the
attached player render layer. This avoids the two-player overlap caused by hiding
model parts before Minecraft schedules the deferred submission.

The reusable animation data is in:

`src/main/resources/assets/player_model/animations/run.json`

After replacing that file, run `build.ps1` again and replace the jar in the Minecraft `mods` directory.
