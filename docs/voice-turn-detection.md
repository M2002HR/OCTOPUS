# Voice turn detection

The turn detector is designed to avoid both common failures: interrupting a natural mid-sentence
pause and leaving the caller waiting after finishing a sentence.

1. Incoming 16-bit PCM is measured with RMS energy.
2. Speech must persist for `VOICE_AGENT_VAD_START_MS` before a turn starts.
3. `VOICE_AGENT_VAD_PRE_ROLL_MS` of preceding PCM is included, preserving initial consonants.
4. The start and continuation RMS thresholds form hysteresis, reducing chatter near the threshold.
5. A turn ends after uninterrupted quiet of `VOICE_AGENT_VAD_END_SILENCE_MS`.
6. Very short/noisy turns below `VOICE_AGENT_VAD_MIN_UTTERANCE_MS` are discarded.
7. `VOICE_AGENT_MAX_TURN_SECONDS` forces a bounded turn for a caller who never pauses.

Frame duration is calculated from the actual PCM byte length, sample rate, and channel count. It
does not assume every native media frame is 20 ms.

## Recommended tuning

| Situation | Change |
| --- | --- |
| Replies feel delayed | Lower `VAD_END_SILENCE_MS` in 50–100 ms steps; 450–600 is a useful range. |
| Caller is interrupted during pauses | Raise `VAD_END_SILENCE_MS`; 700–900 handles deliberate speech well. |
| Background noise creates turns | Raise `VAD_START_RMS` and `VAD_MIN_UTTERANCE_MS`. |
| Quiet speakers are missed | Lower both RMS values while keeping `CONTINUE_RMS <= START_RMS`. |
| First syllable is missing | Raise `VAD_PRE_ROLL_MS` to 250–300. |

Tune one setting at a time using captured PCM fixtures and a real call in the target network.
