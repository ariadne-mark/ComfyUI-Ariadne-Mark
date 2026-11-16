# Example workflows

- `image-workflow.json`: open/drag into the ComfyUI canvas.
- `image-api.json`: submit as the `prompt` property to `/prompt`.
- `video-api.json`: procedural image-to-video smoke workflow; change `video_profile` to any of the three supported modes.
- `saved-file-api.json`: final-file integration without re-encoding the source first.

The loader filenames refer to the unmarked `input.png`/`input.mp4` in the [SDK sample archive](https://github.com/ariadne-mark/ariadne-mark/releases/tag/v0.7.3a4). Put them in ComfyUI/input as `ariadne-unmarked.png` and `ariadne-unmarked.mp4`. Replace the fixture loader with your actual generator for use in your own pipeline. No model weights are included.

These deterministic fixtures make no claim that a generative model produced the test input. The qualification uses a development kit.
