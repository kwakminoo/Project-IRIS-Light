"""ECG-style mic bar wave helpers."""

from __future__ import annotations

from unittest import TestCase

from iris.ui.widgets.mic_waveform_bar import ecg_pulse, ecg_wave_offset, wave_peak_amp


class EcgWaveTests(TestCase):
    def test_pulse_has_sharp_spike(self) -> None:
        us = [i / 200 for i in range(201)]
        peak = max(ecg_pulse(u) for u in us)
        trough = min(ecg_pulse(u) for u in us)
        # 위아래 모두 충분히 튐
        self.assertGreater(peak, 0.8)
        self.assertLess(trough, -0.8)
        self.assertAlmostEqual(ecg_pulse(0.5), 0.0, places=1)

    def test_pulse_is_symmetric_up_and_down(self) -> None:
        """펄스가 위(양수)와 아래(음수) 모두 0.8 이상."""
        us = [i / 200 for i in range(201)]
        peak = max(ecg_pulse(u) for u in us)
        trough = min(ecg_pulse(u) for u in us)
        self.assertGreater(peak, 0.8)
        self.assertLess(trough, -0.8)

    def test_edge_amplitude_smaller_than_center(self) -> None:
        # 중앙(t=0.5) 근방이 가장자리(t=0.05)보다 크거나 같음 (center envelope)
        ts_center = [0.40 + i * 0.01 for i in range(21)]
        ts_edge = [0.02, 0.03, 0.04, 0.05]
        center_max = max(abs(ecg_wave_offset(t, 1.0, 0, 0.5)) for t in ts_center)
        edge_max = max(abs(ecg_wave_offset(t, 1.0, 0, 0.5)) for t in ts_edge)
        self.assertGreater(center_max, edge_max)

    def test_voice_raises_center_spike(self) -> None:
        ts = [0.35 + i * 0.005 for i in range(31)]
        quiet = max(abs(ecg_wave_offset(t, 1.0, layer, 0.0)) for t in ts for layer in range(3))
        loud = max(abs(ecg_wave_offset(t, 1.0, layer, 1.0)) for t in ts for layer in range(3))
        self.assertGreater(loud, quiet)
        self.assertGreater(loud, 0.55)

    def test_peak_amp_grows_with_voice(self) -> None:
        idle = wave_peak_amp(100.0, listening=True, level=0.0)
        loud = wave_peak_amp(100.0, listening=True, level=1.0)
        self.assertGreater(loud, idle)
