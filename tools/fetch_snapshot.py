"""Download only the pinned archives needed for this portfolio."""
from pathlib import Path
import argparse,hashlib,json,tarfile,urllib.request
ROOT=Path(__file__).resolve().parents[1]

def fetch(destination):
    destination.mkdir(parents=True,exist_ok=True)
    cache=destination.parent/'archives';cache.mkdir(exist_ok=True)
    manifest=json.loads((ROOT/'data/source_manifest.json').read_text())
    for item in manifest['files']:
        archive=cache/item['name']
        if not archive.exists():
            with urllib.request.urlopen(item['url'],timeout=180) as response:
                archive.write_bytes(response.read())
        if hashlib.sha256(archive.read_bytes()).hexdigest()!=item['sha256']:
            raise ValueError(f"Checksum mismatch: {archive.name}")
        expected=item['name'].removesuffix('.tar.xz')+'.csv'
        with tarfile.open(archive) as tar:
            matches=[m for m in tar.getmembers() if m.isfile() and Path(m.name).name==expected]
            if len(matches)!=1:raise ValueError(f'Unexpected archive members: {archive.name}')
            with tar.extractfile(matches[0]) as content:(destination/expected).write_bytes(content.read())
        print(archive.name,'verified',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--destination',type=Path,default=ROOT/'data/raw/snapshot')
    fetch(parser.parse_args().destination)
