"""Tests for CID XHTML parser."""

from pathlib import Path

import pytest

from dcmterms.parse_cid import parse_cid_file

FIXTURES = Path(__file__).parent / "fixtures"


class TestCID10:
    """CID 10: 5-column table, SCT + NCIt codes, no includes."""

    @pytest.fixture(autouse=True)
    def parse(self):
        self.result = parse_cid_file(FIXTURES / "sect_CID_10.html")

    def test_metadata(self):
        m = self.result.metadata
        assert m.cid_number == 10
        assert m.cid_name == "Interventional Drug"
        assert m.cid_type == "extensible"
        assert m.keyword == "InterventionalDrug"
        assert m.version == "20260321"
        assert m.uid == "1.2.840.10008.6.1.8"

    def test_entries_count(self):
        assert len(self.result.entries) == 45

    def test_no_includes(self):
        assert self.result.includes == []

    def test_has_sct(self):
        schemes = {e.coding_scheme_designator for e in self.result.entries}
        assert "SCT" in schemes

    def test_first_entry(self):
        e = self.result.entries[0]
        assert e.code_value == "419442005"
        assert e.code_meaning == "Ethanol"
        assert e.snomed_rt_id == "C-21047"
        assert e.umls_concept_uid == "C0001962"


class TestCID29:
    """CID 29: 3-column table, all DCM, 1 include."""

    @pytest.fixture(autouse=True)
    def parse(self):
        self.result = parse_cid_file(FIXTURES / "sect_CID_29.html")

    def test_metadata(self):
        m = self.result.metadata
        assert m.cid_number == 29
        assert m.cid_name == "Acquisition Modality"

    def test_entries_are_dcm(self):
        assert len(self.result.entries) > 0
        for entry in self.result.entries:
            assert entry.coding_scheme_designator == "DCM"

    def test_no_snomed_columns(self):
        for entry in self.result.entries:
            assert entry.snomed_rt_id is None
            assert entry.umls_concept_uid is None

    def test_includes(self):
        assert self.result.includes == [34]

    def test_first_entry(self):
        e = self.result.entries[0]
        assert e.code_value == "AR"
        assert e.code_meaning == "Autorefraction"


class TestCID4:
    """CID 4: 5-column table with 3 includes at top, then direct entries."""

    @pytest.fixture(autouse=True)
    def parse(self):
        self.result = parse_cid_file(FIXTURES / "sect_CID_4.html")

    def test_metadata(self):
        m = self.result.metadata
        assert m.cid_number == 4
        assert m.cid_name == "Anatomic Region"

    def test_includes(self):
        assert self.result.includes == [4030, 4040, 4042]

    def test_has_entries(self):
        assert len(self.result.entries) > 0

    def test_first_entry(self):
        e = self.result.entries[0]
        assert e.coding_scheme_designator == "SCT"
        assert e.code_value == "59652004"
        assert e.code_meaning == "Atrium"


class TestCID7150:
    """CID 7150: 6-column table with per-row context group CID references."""

    @pytest.fixture(autouse=True)
    def parse(self):
        self.result = parse_cid_file(FIXTURES / "sect_CID_7150.html")

    def test_metadata(self):
        m = self.result.metadata
        assert m.cid_number == 7150
        assert m.cid_name == "Segmentation Property Category"
        assert m.cid_type == "extensible"

    def test_entries_count(self):
        assert len(self.result.entries) == 9

    def test_no_includes(self):
        assert self.result.includes == []

    def test_all_entries_have_context_group_cid(self):
        for entry in self.result.entries:
            assert entry.context_group_cid is not None

    def test_context_group_cids(self):
        expected = {7191, 7192, 7193, 7194, 7195, 7196, 7197, 7198, 7164}
        actual = {e.context_group_cid for e in self.result.entries}
        assert actual == expected

    def test_first_entry(self):
        e = self.result.entries[0]
        assert e.coding_scheme_designator == "SCT"
        assert e.code_value == "85756007"
        assert e.code_meaning == "Tissue"
        assert e.context_group_cid == 7191


class TestCID7194:
    """CID 7194: pure aggregator — only Include rows, no direct coded entries."""

    @pytest.fixture(autouse=True)
    def parse(self):
        self.result = parse_cid_file(FIXTURES / "sect_CID_7194.html")

    def test_metadata(self):
        m = self.result.metadata
        assert m.cid_number == 7194
        assert "Morphologically Abnormal Structure" in m.cid_name

    def test_no_entries(self):
        assert self.result.entries == []

    def test_includes(self):
        assert self.result.includes == [7159, 7199]


class TestCID26:
    """CID 26: 5-column table, 1 include. Retired SRT codes in note section should be excluded."""

    @pytest.fixture(autouse=True)
    def parse(self):
        self.result = parse_cid_file(FIXTURES / "sect_CID_26.html")

    def test_metadata(self):
        m = self.result.metadata
        assert m.cid_number == 26
        assert m.cid_name == "Nuclear Medicine Projection"

    def test_includes(self):
        assert self.result.includes == [27]

    def test_no_srt_entries(self):
        """Retired SRT codes are in a note section, not the main table."""
        srt = [e for e in self.result.entries if e.coding_scheme_designator == "SRT"]
        assert len(srt) == 0

    def test_all_sct(self):
        for entry in self.result.entries:
            assert entry.coding_scheme_designator == "SCT"
