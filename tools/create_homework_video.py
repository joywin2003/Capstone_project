"""Create a 5-minute MP4 walkthrough with explicitly synthetic narration.

Optional macOS tooling only: pip install pillow imageio-ffmpeg
Run from the repository root. Uses installed macOS Samantha speech; no online API.
The video is a narrated code walkthrough with captured command output, not a
recording of a student speaking or a live screen capture.
"""

from pathlib import Path
import re
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFont
import imageio_ffmpeg

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'docs/homework2-demo.mp4'


def run(*args):
    return subprocess.run(args, check=True, cwd=ROOT, capture_output=True, text=True).stdout


def main():
    demo = run(sys.executable, '-m', 'backend.streaming.demo')
    tests = run(sys.executable, '-m', 'pytest', 'tests/test_streaming.py', '-q')
    chapters = [
        ('Energy events for German properties', [
            'Homework 2 | Smart Energy Management',
            '',
            'Historical interval readings -> event iterator',
            '                            -> usage filter',
            '                            -> metrics transformer',
            '',
            'Scope: electricity, sample buildings, historical replay',
            'No physical IoT meter or live AI integration is claimed.',
            '',
            'Power kW = interval kWh * 60 / interval minutes',
            '0.5 kWh over 15 minutes = 2.0 kW',
        ], '''This is an automated narrated walkthrough of the smart energy management homework. The project monitors historical electricity consumption for German properties. Instead of connecting physical smart meters, it replays historical interval readings as individual events. The framework applies a usage filter and then transforms accepted events into energy insights. This walkthrough demonstrates the required Python concepts: abstract base classes, inheritance and polymorphism, operator overloading, and iterators with generators. Each event carries building and meter identifiers, a timezone aware timestamp, interval energy, duration, and an activity flag. Energy and power have different units: half a kilowatt hour over fifteen minutes corresponds to two kilowatts of average power.'''),
        ('An abstract contract and specialized processors', [
            'class StreamProcessor(ABC):',
            '    @abstractmethod',
            '    def process(self, event):',
            '        "Return an event, result, or None."',
            '',
            'class ActiveMeterFilter(StreamProcessor):',
            '    def process(self, event): ...',
            '',
            'class EnergyMetricsTransformer(StreamProcessor):',
            '    def process(self, event): ...',
            '',
            'The pipeline calls the same process() API on every stage.',
        ], '''The abstract StreamProcessor defines the contract for every processing stage. Its process method is decorated with abstractmethod. Python therefore prevents constructing this base class until a concrete subclass implements the required behavior. ActiveMeterFilter and EnergyMetricsTransformer inherit from that interface and each provide their own process method. This is inheritance. The pipeline does not need separate code paths for each concrete class. It calls process on every stage using the same interface, which demonstrates polymorphism. A stage may return its accepted event, produce a transformed result, or return None to intentionally drop an event. The pipeline stops processing a dropped event before the next stage runs.'''),
        ('Filtering and transforming energy readings', [
            'ActiveMeterFilter(min_power_kw=0.1)',
            '  active=False                -> drop',
            '  energy=0.01 kWh / 15 min     -> 0.04 kW -> drop',
            '  energy=0.025 kWh / 15 min    -> 0.10 kW -> retain',
            '',
            'EnergyMetricsTransformer(',
            '    eur_per_kwh=0.30, kg_co2_per_kwh=0.38)',
            '',
            'For 0.5 kWh:',
            '  power = 2.0 kW',
            '  estimated cost = 0.15 EUR',
            '  estimated emissions = 0.19 kg CO2',
        ], '''The filter first checks whether the meter is active. It then compares average power with a configurable minimum threshold. In the sample, the threshold is zero point one kilowatts. An inactive meter is dropped. An event with zero point zero one kilowatt hours over fifteen minutes represents zero point zero four kilowatts and is also dropped. An event exactly at the threshold is retained. The transformer calculates cost and carbon emissions using demonstration factors. Half a kilowatt hour at thirty cents per kilowatt hour costs fifteen cents, and produces an estimate of zero point one nine kilograms of carbon dioxide. These factors are configurable assumptions, not current tariff claims.'''),
        ('Operator overloading composes the pipeline', [
            'pipeline = (',
            '    ActiveMeterFilter(min_power_kw=0.1)',
            '    + EnergyMetricsTransformer()',
            ')',
            '',
            'def __add__(self, other):',
            '    return Pipeline((self, other))',
            '',
            'Pipeline.__add__ also supports chained composition.',
            'Execution order is preserved from left to right.',
            'Counters record received, emitted, and dropped events.',
        ], '''Operator overloading makes the framework easy to compose. The plus operator between two processors invokes the overloaded add method and creates a Pipeline. The filter appears first and the metrics transformer appears second, so transformation happens only for accepted events. The Pipeline also implements the same processor interface and supports additional stages through chained addition. It records how many inputs were received, how many results were emitted, and how many events were deliberately dropped. Those counters make the demonstration inspectable. Invalid event types and incompatible stage order produce a clear processing error, rather than silently returning misleading metrics. The automated tests verify stage order and that dropped inputs never reach the transformer.'''),
        ('Explicit iterator and lazy generator consumption', [
            'class HistoricalEnergyStream:',
            '    def __iter__(self):',
            '        return self',
            '    def __next__(self):',
            '        return next(self._events)',
            '',
            'def run(self, events):',
            '    for event in events:',
            '        result = self.process(event)',
            '        if result is not None:',
            '            yield result',
            'No source input is consumed before output is requested.',
        ], '''HistoricalEnergyStream explicitly implements the iterator protocol. Iter returns the stream itself. Next consumes one event from the underlying source. When that source is exhausted, StopIteration propagates naturally and the for loop ends. The CSV source uses a generator to open and read the small fixture lazily. Pipeline run is also a generator: it yields results as they become available instead of collecting a full output list. Nothing is processed until the consumer requests an output. A laziness test uses a counter to prove that requesting one output does not consume the whole source. The full OPSD preparation still uses Pandas, so this prototype does not claim constant memory ingestion for the entire raw dataset.'''),
        ('Executed demo and verification', [
            '$ python -m backend.streaming.demo',
            '',
            'First result: power=2.0 kW, cost=0.15 EUR, CO2=0.19 kg',
            next(line for line in demo.splitlines() if line.startswith('received=')),
            '',
            '$ python -m pytest tests/test_streaming.py -q',
            tests.strip().splitlines()[-1],
            '',
            'OPSD replay uses the same filter + transformer classes.',
            'All valid interval energy is persisted for reporting.',
            'Only the derived insight stream applies the usage filter.',
        ], '''The final card contains output captured by executing the project commands while generating this video. The fixture contains five inputs. Three are emitted, and two are dropped: one inactive meter and one below the threshold. The first accepted event produces two kilowatts, fifteen cents of estimated cost, and zero point one nine kilograms of carbon dioxide. The stream tests pass, including iterator exhaustion, threshold boundaries, composition, units, invalid input, and generator laziness. The OPSD replay uses the same processors. All valid energy remains in storage, because filtering small readings out of authoritative consumption totals would distort reports. The README contains the class diagrams, installation commands, branch information, and this video link. Student identification should be checked before academic submission.'''),
    ]
    encoder = imageio_ffmpeg.get_ffmpeg_exe()
    font_path = '/System/Library/Fonts/Menlo.ttc'
    title_font = ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc', 38)
    code_font = ImageFont.truetype(font_path, 23)
    small_font = ImageFont.truetype(font_path, 17)
    with tempfile.TemporaryDirectory(prefix='capstone-video-') as folder:
        temp = Path(folder)
        parts = []
        for i, (title, lines, narration) in enumerate(chapters):
            card = Image.new('RGB', (1280, 720), '#1e3045')
            draw = ImageDraw.Draw(card)
            draw.rectangle((0, 0, 1280, 12), fill='#c09262')
            draw.text((52, 43), title, font=title_font, fill='#f3eadf')
            draw.text((52, 106), f'CHAPTER {i+1}/6  |  HOMEWORK 2  |  HISTORICAL ENERGY REPLAY', font=small_font, fill='#c09262')
            draw.rounded_rectangle((35, 153, 1245, 620), radius=15, fill='#142334')
            for j, line in enumerate(lines):
                draw.text((58, 173 + 32*j), line, font=code_font, fill='#f3eadf')
            draw.text((48, 656), 'Automated code walkthrough | Synthetic narration | 05:00 total', font=small_font, fill='#c09262')
            png = temp / f'card{i}.png'
            card.save(png)
            narration_file = temp / f'narration{i}.txt'
            narration_file.write_text(narration)
            audio = temp / f'audio{i}.aiff'
            run('say', '-v', 'Samantha', '-r', str(215 if i == 5 else 180), '-f', str(narration_file), '-o', str(audio))
            info = run('afinfo', str(audio))
            duration = float(re.search(r'estimated duration:\s*([0-9.]+)', info).group(1))
            if not 1 < duration < 49.5:
                raise RuntimeError(f'Unexpected narration duration {duration} in chapter {i+1}')
            part = temp / f'part{i}.mp4'
            run(encoder, '-y', '-loglevel', 'error', '-loop', '1', '-framerate', '10', '-i', str(png),
                '-i', str(audio), '-af', 'apad', '-t', '50', '-c:v', 'libx264', '-preset', 'veryfast',
                '-crf', '25', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '64k', '-movflags', '+faststart', str(part))
            parts.append(part)
            print(f'Chapter {i+1}: voice={duration:.1f}s, video=50s', flush=True)
        listing = temp / 'concat.txt'
        listing.write_text(''.join(f"file '{part}'\n" for part in parts))
        run(encoder, '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', str(listing),
            '-c', 'copy', '-movflags', '+faststart', str(OUTPUT))
        print(f'Created {OUTPUT} ({OUTPUT.stat().st_size / 1024 / 1024:.2f} MiB)', flush=True)


if __name__ == '__main__':
    main()
