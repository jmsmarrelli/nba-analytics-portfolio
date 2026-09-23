"""Shared colors, typography and export settings for the Python figures."""

from __future__ import annotations
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

# --------------------------------------------------------------------------
# Palette
# --------------------------------------------------------------------------

CATEGORICAL = [
    "#2a78d6",  # blue
    "#eb6834",  # orange
    "#1baf7a",  # aqua
    "#eda100",  # yellow
    "#e87ba4",  # magenta
    "#008300",  # green
    "#4a3aa7",  # violet
    "#e34948",  # red
]

SEQUENTIAL_BLUE = [
    "#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec",
    "#5598e7", "#3987e5", "#2a78d6", "#256abf", "#1c5cab",
    "#184f95", "#104281", "#0d366b",
]

DIVERGING = ["#104281", "#2a78d6", "#86b6ef", "#f0efec",
             "#f0a3a2", "#e34948", "#9e2322"]

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#8a8880"
GRID = "#e5e4e0"

# Team accents used when the Spurs are compared against the field.
SPURS_COLOR = "#2a78d6"
FIELD_COLOR = "#b8b6ae"
HIGHLIGHT = "#eb6834"

seq_cmap = LinearSegmentedColormap.from_list("nbalab_seq", SEQUENTIAL_BLUE)
div_cmap = LinearSegmentedColormap.from_list("nbalab_div", DIVERGING)


def use_theme() -> None:
    """Install the repository chart theme into matplotlib's rcParams."""
    mpl.rcParams.update({
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "savefig.dpi": 200,
        "savefig.bbox": "tight",
        "figure.dpi": 110,

        "font.family": "DejaVu Sans",
        "font.size": 10.5,
        "text.color": INK,

        "axes.edgecolor": GRID,
        "axes.labelcolor": INK_SECONDARY,
        "axes.labelsize": 10,
        "axes.titlesize": 13,
        "axes.titleweight": "semibold",
        "axes.titlecolor": INK,
        "axes.titlelocation": "left",
        "axes.titlepad": 14,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "axes.axisbelow": True,
        "axes.prop_cycle": mpl.cycler(color=CATEGORICAL),

        "grid.color": GRID,
        "grid.linewidth": 0.8,

        "xtick.color": INK_MUTED,
        "ytick.color": INK_MUTED,
        "xtick.labelcolor": INK_SECONDARY,
        "ytick.labelcolor": INK_SECONDARY,
        "xtick.labelsize": 9.5,
        "ytick.labelsize": 9.5,
        "xtick.major.size": 0,
        "ytick.major.size": 0,

        "legend.frameon": False,
        "legend.fontsize": 9.5,
        "legend.labelcolor": INK_SECONDARY,

        "lines.linewidth": 2.0,
        "lines.markersize": 6,
        "patch.linewidth": 0,
    })


def annotate(ax, title: str, subtitle: str | None = None,
             source: str | None = None) -> None:
    """Title block plus an optional source line, applied consistently."""
    ax.set_title(title, pad=22 if subtitle else 14)
    if subtitle:
        ax.text(0, 1.02, subtitle, transform=ax.transAxes,
                fontsize=10, color=INK_SECONDARY, va="bottom")
    if source:
        ax.figure.text(0.0, -0.02, source, fontsize=8.5, color=INK_MUTED,
                       ha="left", va="top", transform=ax.transAxes)


def save(fig, path, **kwargs) -> None:
    fig.savefig(path, metadata={"Software": None}, **kwargs)
    fig.savefig(Path(path).with_suffix(".svg"), metadata={"Creator": None, "Date": None}, **kwargs)
    plt.close(fig)
