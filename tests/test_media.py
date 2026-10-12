import io
import wave

from phonix.services import media


def _wav(rate=44100, channels=2, seconds=0.2):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(b"\x10\x00" * int(rate * seconds) * channels)
    return buf.getvalue()


def test_python_conversion(tmp_path):
    src, dst = tmp_path / "in.wav", tmp_path / "out.wav"
    src.write_bytes(_wav())
    media._convert_wav(src, dst)
    with wave.open(str(dst)) as wf:
        assert (wf.getframerate(), wf.getnchannels(), wf.getsampwidth()) == (8000, 1, 2)
        assert abs(wf.getnframes() - 1600) <= 2


def test_upload_sets_custom_moh(session, monkeypatch):
    from phonix.core import settings as st

    monkeypatch.setattr(media.shutil, "which", lambda _name: None)
    item = media.add_media(session, "moh", "My Song!.wav", _wav())
    assert item.path == "moh/My_Song.wav"
    assert st.load(session, st.MediaSettings).custom_moh
    media.delete_media(session, item.id)
    assert not st.load(session, st.MediaSettings).custom_moh
