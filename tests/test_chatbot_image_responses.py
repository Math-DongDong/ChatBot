import re
import unittest
from pathlib import Path
from types import SimpleNamespace


module_path = Path(__file__).resolve().parents[1] / "ChatBot.py"
source = module_path.read_text(encoding="utf-8")
match = re.search(r"def extract_response_parts\(response\):.*?return \"\\n\"\.join\(text_output\)\.strip\(\), image_outputs", source, re.S)
if not match:
    raise RuntimeError("extract_response_parts function not found")

namespace = {}
exec(match.group(0), namespace)
extract_response_parts = namespace["extract_response_parts"]


class PartWithInlineData:
    def __init__(self):
        self.inline_data = SimpleNamespace(data=b"image-bytes", mime_type="image/png")

    @property
    def text(self):
        raise ValueError("Could not convert `part.inline_data` to text")


class ChatBotImageResponseTests(unittest.TestCase):
    def test_extract_response_parts_handles_inline_data_without_text(self):
        response = SimpleNamespace(
            candidates=[SimpleNamespace(content=SimpleNamespace(parts=[PartWithInlineData()]))]
        )

        text_output, image_outputs = extract_response_parts(response)

        self.assertEqual(text_output, "")
        self.assertEqual(image_outputs, [(b"image-bytes", "image/png")])


if __name__ == "__main__":
    unittest.main()
