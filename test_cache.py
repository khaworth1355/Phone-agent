"""
Test script to verify cache generation works
"""
import asyncio
import sys
from elevenlabs_client import ElevenLabsClient
from config import Config

async def test_cache_generation():
    """Test if ElevenLabs cache generation works"""

    print("="*80)
    print("TESTING CACHE GENERATION")
    print("="*80)
    print(f"ElevenLabs API Key configured: {bool(Config.ELEVENLABS_API_KEY)}")
    print(f"ElevenLabs Voice ID: {Config.ELEVENLABS_VOICE_ID}")
    print(f"ElevenLabs Model: {Config.ELEVENLABS_MODEL}")
    print("="*80 + "\n")

    # Test text
    test_text = "The owner of TEMCO is Mark Hayworth."

    try:
        print(f"Testing TTS generation...")
        print(f"Text: '{test_text}'")
        print()

        # Create client
        tts = ElevenLabsClient()

        # Generate audio
        print("Calling ElevenLabs API...")
        audio_bytes = await tts.text_to_speech(test_text)

        if audio_bytes:
            print(f"✅ SUCCESS!")
            print(f"   Generated {len(audio_bytes)} bytes of audio")
            print(f"   Duration: ~{len(audio_bytes) / 8000:.1f} seconds")
            print()
            print("Cache generation should work! ✅")
            return True
        else:
            print("❌ FAILED: No audio returned")
            print()
            print("This is why cache generation is failing!")
            return False

    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        print()
        print("This is why cache generation is failing!")
        return False

if __name__ == "__main__":
    print("\n")
    result = asyncio.run(test_cache_generation())
    print("\n" + "="*80)
    if result:
        print("DIAGNOSIS: Cache system should work on server")
    else:
        print("DIAGNOSIS: Cache system is broken - see errors above")
    print("="*80 + "\n")
    sys.exit(0 if result else 1)