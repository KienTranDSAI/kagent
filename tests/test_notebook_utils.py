import json

import pytest

from kagent.tools.notebook_utils import (
    count_cells_by_type,
    format_notebook_text,
    read_notebook,
    validate_notebook,
)


SAMPLE_NB = {
    "cells": [
        {
            "cell_type": "markdown",
            "source": ["# Title\n", "intro text"],
        },
        {
            "cell_type": "code",
            "source": "print(1 + 1)",
            "outputs": [
                {"output_type": "stream", "name": "stdout", "text": "2\n"},
            ],
        },
        {
            "cell_type": "code",
            "source": "1 / 0",
            "outputs": [
                {
                    "output_type": "error",
                    "ename": "ZeroDivisionError",
                    "evalue": "division by zero",
                    "traceback": ["Traceback...", "ZeroDivisionError: division by zero"],
                }
            ],
        },
    ],
    "nbformat": 4,
    "nbformat_minor": 5,
}


@pytest.fixture
def nb_file(tmp_path):
    p = tmp_path / "test.ipynb"
    p.write_text(json.dumps(SAMPLE_NB), encoding="utf-8")
    return str(p)


def test_validate_ok(nb_file):
    ok, err = validate_notebook(nb_file)
    assert ok and err is None


def test_validate_missing():
    ok, err = validate_notebook("/tmp/does-not-exist-xyz.ipynb")
    assert not ok
    assert "not found" in err.lower()


def test_validate_dir(tmp_path):
    ok, err = validate_notebook(str(tmp_path))
    assert not ok
    assert "directory" in err.lower()


def test_validate_empty(tmp_path):
    p = tmp_path / "empty.ipynb"
    p.write_bytes(b"")
    ok, err = validate_notebook(str(p))
    assert not ok
    assert "empty" in err.lower()


def test_read_cells(nb_file):
    cells = read_notebook(nb_file)
    assert len(cells) == 3
    assert cells[0]["cell_type"] == "markdown"
    assert "# Title" in cells[0]["source"]
    assert "intro text" in cells[0]["source"]
    assert cells[1]["cell_type"] == "code"
    assert "stream" in cells[1]["outputs"][0]
    assert "ZeroDivisionError" in cells[2]["outputs"][0]


def test_read_no_cells_field(tmp_path):
    p = tmp_path / "nocells.ipynb"
    p.write_text(json.dumps({"nbformat": 4}), encoding="utf-8")
    cells = read_notebook(str(p))
    assert cells == []


def test_read_invalid_json(tmp_path):
    p = tmp_path / "broken.ipynb"
    p.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        read_notebook(str(p))


def test_format_text(nb_file):
    cells = read_notebook(nb_file)
    text = format_notebook_text(cells)
    assert "[Cell 1: markdown]" in text
    assert "[Cell 2: code]" in text
    assert "--- outputs ---" in text
    assert "ZeroDivisionError" in text


def test_count_types(nb_file):
    cells = read_notebook(nb_file)
    counts = count_cells_by_type(cells)
    assert counts == {"markdown": 1, "code": 2}


def test_format_handles_image_output(tmp_path):
    nb = {
        "cells": [
            {
                "cell_type": "code",
                "source": "import matplotlib.pyplot as plt; plt.plot([1,2])",
                "outputs": [
                    {
                        "output_type": "display_data",
                        "data": {
                            "image/png": "A" * 4096,   # ~3 KB raw
                            "text/plain": "<matplotlib.lines.Line2D ...>",
                        },
                    }
                ],
            }
        ],
        "nbformat": 4,
    }
    p = tmp_path / "plot.ipynb"
    p.write_text(json.dumps(nb), encoding="utf-8")
    cells = read_notebook(str(p))
    text = format_notebook_text(cells)
    assert "image output image/png" in text
    assert "matplotlib.lines.Line2D" in text
