from dataclasses import replace
from datetime import datetime, timezone

import pytest

from backend.streaming.events import EnergyEvent, StreamProcessingError
from backend.streaming.processors import ActiveMeterFilter, EnergyMetricsTransformer, StreamProcessor
from backend.streaming.source import HistoricalEnergyStream


@pytest.fixture
def event():
    return EnergyEvent(1, 1, datetime(2016, 12, 1, tzinfo=timezone.utc), 0.5)


def test_processor_requires_concrete_process():
    with pytest.raises(TypeError):
        StreamProcessor()


def test_energy_stream_iterator_exhaustion(event):
    stream = HistoricalEnergyStream([event])
    assert iter(stream) is stream
    assert next(stream) == event
    with pytest.raises(StopIteration):
        next(stream)


def test_inactive_meter_is_dropped(event):
    assert ActiveMeterFilter().process(replace(event, active=False)) is None


def test_power_filter_respects_threshold(event):
    stage = ActiveMeterFilter(0.1)
    assert stage.process(replace(event, energy_kwh=0.01)) is None
    assert stage.process(replace(event, energy_kwh=0.025)) is not None
    assert stage.process(event) == event


def test_metrics_transformer_calculates_units(event):
    result = EnergyMetricsTransformer().process(event)
    assert result.power_kw == 2
    assert result.cost_eur == pytest.approx(0.15)
    assert result.co2_kg == pytest.approx(0.19)
    assert result.event == event


def test_pipeline_addition_preserves_order(event):
    pipeline = ActiveMeterFilter() + ActiveMeterFilter(1) + EnergyMetricsTransformer()
    results = list(pipeline.run([replace(event, active=False), event]))
    assert len(results) == 1
    assert results[0].power_kw == 2
    assert (pipeline.received, pipeline.emitted, pipeline.dropped) == (2, 1, 1)


def test_pipeline_generator_is_lazy(event):
    consumed = []

    def source():
        for i in range(3):
            consumed.append(i)
            yield event

    output = (ActiveMeterFilter() + EnergyMetricsTransformer()).run(source())
    assert consumed == []
    next(output)
    assert consumed == [0]


def test_invalid_event_and_stage_are_rejected(event):
    with pytest.raises(StreamProcessingError):
        replace(event, energy_kwh=float("nan"))
    with pytest.raises(StreamProcessingError):
        replace(event, interval_minutes=0)
    with pytest.raises(StreamProcessingError):
        (EnergyMetricsTransformer() + ActiveMeterFilter()).process(event)


def test_csv_fixture_filters_two_events():
    from pathlib import Path
    fixture = Path(__file__).parents[1] / "data/sample/energy_events.csv"
    pipeline = ActiveMeterFilter() + EnergyMetricsTransformer()
    assert len(list(pipeline.run(HistoricalEnergyStream.from_csv(fixture)))) == 3
    assert pipeline.dropped == 2
