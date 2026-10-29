import unittest

from audio.microphone import SilenceSegmenter


class SilenceSegmenterTests(unittest.TestCase):
    def test_silence_alone_does_not_create_an_utterance(self):
        segmenter = SilenceSegmenter(rms_threshold=10, silence_seconds=0.2)
        silence = b"\x00\x00" * 1600

        self.assertIsNone(segmenter.add_frame(silence, rms=0))
        self.assertIsNone(segmenter.add_frame(silence, rms=0))
        self.assertIsNone(segmenter.add_frame(silence, rms=0))

    def test_speech_is_returned_after_a_pause(self):
        segmenter = SilenceSegmenter(
            rms_threshold=10,
            silence_seconds=0.2,
            min_speech_seconds=0.2,
        )
        speech = b"\x01\x00" * 1600
        silence = b"\x00\x00" * 1600

        self.assertIsNone(segmenter.add_frame(speech, rms=20))
        self.assertIsNone(segmenter.add_frame(speech, rms=20))
        self.assertIsNone(segmenter.add_frame(silence, rms=0))
        utterance = segmenter.add_frame(silence, rms=0)

        self.assertIsNotNone(utterance)
        self.assertIn(speech, utterance)

    def test_long_utterance_is_bounded(self):
        segmenter = SilenceSegmenter(
            rms_threshold=10,
            silence_seconds=0.5,
            min_speech_seconds=0.2,
            max_utterance_seconds=0.3,
        )
        speech = b"\x01\x00" * 1600

        self.assertIsNone(segmenter.add_frame(speech, rms=20))
        self.assertIsNone(segmenter.add_frame(speech, rms=20))
        utterance = segmenter.add_frame(speech, rms=20)

        self.assertEqual(utterance, speech * 3)

    def test_reset_discards_buffered_audio(self):
        segmenter = SilenceSegmenter(
            rms_threshold=10,
            silence_seconds=0.2,
            min_speech_seconds=0.2,
        )
        speech = b"\x01\x00" * 1600
        silence = b"\x00\x00" * 1600
        segmenter.add_frame(speech, rms=20)
        segmenter.add_frame(speech, rms=20)
        segmenter.reset()

        self.assertIsNone(segmenter.add_frame(silence, rms=0))
        self.assertIsNone(segmenter.add_frame(silence, rms=0))


if __name__ == "__main__":
    unittest.main()
