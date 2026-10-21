# Wallpaper color variants

These project assets were created with the built-in image-generation tool in edit mode, using `theme/backgrounds/tux-crimson-eclipse.png` as the edit target. The original crimson wallpaper remains unchanged. Each variant was visually inspected for the same scene, Tux pose, eclipse placement, and matching illumination.

Saved files:

- [Original red](../theme/backgrounds/tux-crimson-eclipse.png)
- [Blue](../theme/backgrounds/tux-blue-eclipse.png)
- [Green](../theme/backgrounds/tux-green-eclipse.png)
- [Yellow](../theme/backgrounds/tux-yellow-eclipse.png)
- [Pink](../theme/backgrounds/tux-pink-eclipse.png)
- [Purple](../theme/backgrounds/tux-purple-eclipse.png)

One built-in edit call was made per variant. This exact prompt template was used with `COLOR` replaced by blue, green, yellow, pink, and purple; the first color occurrence was uppercase:

> Use case: lighting-weather edit. Asset type: Linux desktop wallpaper color variant. Edit target: the provided original crimson eclipse/Tux wallpaper. Make a COLOR accent variant by changing ONLY the red/crimson emissive eclipse rim, sky/cloud highlights, reflected light, rivers and rock edge illumination to luminous COLOR, with near-black shadows retained. Preserve exactly the same scene composition, penguin identity and pose, mountain silhouettes, camera framing, eclipse placement, detail, aspect ratio, and overall darkness. Keep the penguin black/white with its natural orange beak and feet. This is a color-only variant, not a new scene. No text, watermark, UI or extra objects.

Existing attribution/licensing notes in the repository README still apply. The installer ships these PNGs directly; it does not call an image API or edit raster images on the user's machine.
