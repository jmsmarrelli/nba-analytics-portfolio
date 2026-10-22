"""Shared editorial chart conventions; no model fitting or data transformations.

AI-assisted visual design, October 2026. Uses system-independent Matplotlib
fonts, deterministic exports and explicit units. Sources retain their own rights.
"""
from pathlib import Path
import textwrap
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

INK = "#172D36"
MUTED = "#5D6B70"
TEAL = "#087E8B"
ORANGE = "#C4512C"
PALE = "#E8EEEF"
PAPER = "#FBFAF6"
GRID = "#DCE3E3"


def canvas(kicker, title, subtitle, height=8.5):
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 11,
        "text.color": INK, "axes.labelcolor": INK,
        "axes.edgecolor": GRID, "xtick.color": MUTED, "ytick.color": INK,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.spines.left": False, "axes.spines.bottom": False,
        "figure.facecolor": PAPER, "axes.facecolor": PAPER,
        "savefig.facecolor": PAPER, "svg.fonttype": "none",
        "svg.hashsalt": "smarrelli-editorial-2026",
    })
    fig = plt.figure(figsize=(14, height))
    fig.text(.045, .947, kicker.upper(), fontsize=10, weight="bold", color=TEAL)
    fig.text(.045, .882, title, fontsize=26, weight="bold")
    fig.text(.045, .835, subtitle, fontsize=11, color=MUTED)
    fig.add_artist(Line2D([.045, .955], [.805, .805], transform=fig.transFigure,
                          color=INK, lw=.8))
    return fig


def note(fig, x, y, heading, body, width=29, color=INK):
    fig.text(x, y, heading, fontsize=11, weight="bold", color=color, va="top")
    fig.text(x, y-.04, textwrap.fill(body, width), fontsize=10.5,
             color=MUTED, va="top", linespacing=1.5)


def stat(fig, x, y, number, label, color=TEAL):
    fig.text(x, y, number, fontsize=29, weight="bold", color=color)
    fig.text(x, y-.035, label, fontsize=10, color=MUTED)


def tidy(ax, axis="x"):
    ax.set_axisbelow(True)
    ax.grid(axis=axis, color=GRID, lw=.7)
    ax.tick_params(axis="both", length=0, pad=8)


def finish(fig, destination, source, method):
    fig.add_artist(Line2D([.045, .955], [.125, .125], transform=fig.transFigure,
                          color=GRID, lw=.8))
    fig.text(.045, .093, source, fontsize=9, color=MUTED)
    fig.text(.045, .065, method, fontsize=9, color=MUTED)
    fig.text(.045, .025, "JOSEPH SMARRELLI  /  BASKETBALL ANALYTICS",
             fontsize=8, weight="bold", color=INK)
    fig.text(.955, .025, "PUBLIC DATA · REPRODUCIBLE FIGURE", fontsize=8,
             ha="right", color=MUTED)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(destination.with_suffix(".png"), dpi=180,
                metadata={"Software": None})
    fig.savefig(destination.with_suffix(".svg"), metadata={
        "Date": None, "Creator": None, "Description": source + " " + method})
    svg = destination.with_suffix(".svg")
    svg.write_text("\n".join(s.rstrip() for s in svg.read_text().splitlines()) + "\n")
    plt.close(fig)
