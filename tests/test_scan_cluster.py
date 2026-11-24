"""Exact clusters: same signature, same cluster; files without messages kept."""

from pathlib import Path

from raphael7.scan.cluster import cluster_by_signature
from raphael7.scan.files import scan_files

SAMPLES = Path(__file__).resolve().parent.parent / "samples"

MSH = "MSH|^~\\&|APP|FAC|||20261124||ADT^A01|{id}|P|2.5\r"


def write(folder: Path, name: str, text: str) -> None:
    (folder / name).write_text(text)


def test_same_shape_same_cluster_biggest_first(tmp_path):
    write(tmp_path, "1.hl7", MSH.format(id=1) + "PID|1||111\r")
    write(tmp_path, "2.hl7", MSH.format(id=2) + "PID|1||222||COHEN\r")
    write(tmp_path, "3.hl7", MSH.format(id=3) + "PID|1||333||LEVI\r")
    grouping = cluster_by_signature(scan_files(tmp_path))

    sizes = []
    for cluster in grouping.clusters:
        sizes.append(len(cluster.members))
    assert sizes == [2, 1]
    first_members = []
    for ref in grouping.clusters[0].members:
        first_members.append(str(ref))
    assert first_members == ["2.hl7#1", "3.hl7#1"]


def test_ties_keep_the_order_first_seen(tmp_path):
    write(tmp_path, "a.hl7", MSH.format(id=1) + "PID|1||111||COHEN\r")
    write(tmp_path, "b.hl7", MSH.format(id=2) + "PID|1||222\r")
    grouping = cluster_by_signature(scan_files(tmp_path))
    assert grouping.clusters[0].members[0].file == "a.hl7"


def test_files_without_messages_are_kept(tmp_path):
    write(tmp_path, "ok.hl7", MSH.format(id=1))
    write(tmp_path, "empty.hl7", "")
    write(tmp_path, "notes.txt", "not a message")
    grouping = cluster_by_signature(scan_files(tmp_path))

    kept = []
    for scanned in grouping.files_without_messages:
        kept.append(scanned.path)
    assert kept == ["empty.hl7", "notes.txt"]


def test_every_sample_message_is_in_exactly_one_cluster():
    message_count = 0
    for scanned in scan_files(SAMPLES):
        message_count += len(scanned.messages)

    grouping = cluster_by_signature(scan_files(SAMPLES))
    refs = []
    for cluster in grouping.clusters:
        refs.extend(cluster.members)
    assert len(refs) == message_count
    assert len(set(refs)) == message_count


def test_each_vendor_admission_shape_is_its_own_cluster():
    grouping = cluster_by_signature(scan_files(SAMPLES))
    vendors = set()
    for cluster in grouping.clusters:
        if cluster.signature.message_type == "ADT^A01" and len(cluster.members) >= 10:
            vendors.add(cluster.members[0].file.split("/")[0])
    assert vendors == {"vendor-a", "vendor-b", "vendor-c"}
