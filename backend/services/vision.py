"""
Vision service using a self-hosted (private) Hugging Face Space for image description.
"""
import os
import json
import base64
import hashlib
import asyncio
import tempfile
from pathlib import Path
from typing import Optional, List, Dict

# pyrefly: ignore [missing-import]
from gradio_client import Client, handle_file


class VisionService:
    """Extract technical details from images using a self-hosted Qwen VL Space"""

    EXTRACTION_PROMPT = """
Extract from this image, for search indexing:
- Type (chart/diagram/table/screenshot/etc.)
- All visible text, labels, and numbers (verbatim)
- Key relationships or trends shown
- A brief summary of the main point

Be factual and concise. Skip anything not visible in the image.
"""

    def __init__(
        self,
        space_name: str = "",
        hf_token: Optional[str] = None,
        cache_path: str = "vision_cache.json",
        max_new_tokens: int = 150,
    ):
        """
        Initialize the vision service.

        Args:
            space_name: Your HF Space, e.g. "your-username/rag-vision-service"
            hf_token: HF token — REQUIRED since the Space is Private. Defaults to HF_TOKEN env var.
            cache_path: Local JSON file used to cache descriptions by image hash,
                        so re-running the pipeline never re-describes the same image twice.
            max_new_tokens: Max tokens the model generates per description (default 150).
        """
        self.hf_token = hf_token or os.getenv("HF_TOKEN")
        self.space_name = space_name or os.getenv("HF_SPACE_NAME")
        if not self.hf_token:
            raise ValueError(
                "HF_TOKEN is required for a private Space (set env var or pass hf_token=...)"
            )

        if not self.space_name:
            raise ValueError("HF_SPACE_NAME is required (set env var or pass space_name=...)")

        self.client = Client(self.space_name, token=self.hf_token, verbose=False)
        self.max_new_tokens = max_new_tokens

        self.cache_path = Path(cache_path)
        self._cache: Dict[str, str] = {}
        if self.cache_path.exists():
            self._cache = json.loads(self.cache_path.read_text(encoding="utf-8"))

    def _save_cache(self):
        self.cache_path.write_text(json.dumps(self._cache, indent=2), encoding="utf-8")

    @staticmethod
    def _hash_image(image_bytes: bytes) -> str:
        return hashlib.sha256(image_bytes).hexdigest()

    def _query_space(self, image_bytes: bytes, image_format: str) -> str:
        """Synchronous call to the Space's /predict endpoint"""
        with tempfile.NamedTemporaryFile(suffix=f".{image_format}", delete=False) as tmp:
            tmp.write(image_bytes)
            tmp_path = tmp.name

        try:
            result = self.client.predict(
                image=handle_file(tmp_path),
                prompt_text=self.EXTRACTION_PROMPT,
                max_new_tokens=self.max_new_tokens,
                api_name="/predict",
            )
            return result
        finally:
            os.unlink(tmp_path)

    async def describe_diagram(
        self,
        image_base64: str,
        image_format: str = "png",
        context: Optional[str] = None,
    ) -> str:
        """
        Generate a searchable description of a diagram or technical image.
        Uses a local disk cache keyed by image content hash, so identical images
        (even across separate runs) are never sent to the Space twice.

        Args:
            image_base64: Base64-encoded image data
            image_format: Image format (png, jpeg, etc.)
            context: Optional context, prepended to the cached/generated description

        Returns:
            Text description of the image
        """
        try:
            image_bytes = base64.b64decode(image_base64)
            key = self._hash_image(image_bytes)

            if key in self._cache:
                description = self._cache[key]
            else:
                loop = asyncio.get_event_loop()
                description = await loop.run_in_executor(
                    None, self._query_space, image_bytes, image_format
                )
                self._cache[key] = description
                self._save_cache()

            if context:
                description = f"Context: {context}\nDescription: {description}"

            return description

        except Exception as e:
            raise RuntimeError(f"Failed to describe image: {str(e)}")

    async def batch_describe(
        self,
        images: List[Dict[str, str]],
        context: Optional[str] = None,
    ) -> List[str]:
        """
        Describe multiple images sequentially.

        ZeroGPU Spaces process one request at a time internally, so running
        concurrent requests just causes queue timeouts and CancelledErrors.
        Sequential processing is more reliable.

        Args:
            images: List of dicts with 'data' (base64) and 'format' keys
            context: Optional context for all images

        Returns:
            List of descriptions (failed images return an empty string)
        """
        descriptions = []
        for idx, img in enumerate(images):
            try:
                desc = await self.describe_diagram(
                    img["data"], img.get("format", "png"), context
                )
                descriptions.append(desc)
                print(f"  [vision] {idx + 1}/{len(images)} done")
            except Exception as e:
                print(f"  [vision] {idx + 1}/{len(images)} FAILED: {e}")
                descriptions.append("")  # Keep list aligned with input
        return descriptions


# CLI interface for testing
if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv

    load_dotenv()

    async def main():
        if len(sys.argv) < 2:
            print("Usage: python vision.py <path_to_parsed_images_json> [space_name]")
            sys.exit(1)

        json_path = Path(sys.argv[1])
        if not json_path.exists():
            print(f"Error: File {json_path} does not exist.")
            sys.exit(1)

        space_name = sys.argv[2] if len(sys.argv) > 2 else os.getenv(
            "HF_SPACE_NAME", "your-username/rag-vision-service"
        )

        print(f"Loading images from {json_path.name}...")
        with open(json_path, "r", encoding="utf-8") as f:
            images = json.load(f)

        if not images:
            print("No images found in the JSON file.")
            return

        service = VisionService(space_name=space_name)
        print(f"Batch describing {len(images)} images via private Space: {space_name}...")

        try:
            descriptions = await service.batch_describe(images, context="CLI testing")

            for idx, desc in enumerate(descriptions, 1):
                print("\n" + "=" * 40)
                print(f"IMAGE {idx} DESCRIPTION:")
                print("=" * 40)
                print(desc)

        except Exception as e:
            print(f"Error calling Vision API: {e}")

    asyncio.run(main())
