# Shared base-R plotting colors and helpers.
# Colors match nbalab/viz.py.

PALETTE <- c(
  blue    = "#2a78d6",
  orange  = "#eb6834",
  aqua    = "#1baf7a",
  yellow  = "#eda100",
  magenta = "#e87ba4",
  green   = "#008300",
  violet  = "#4a3aa7",
  red     = "#e34948"
)

SEQ_BLUE <- c("#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec",
              "#5598e7", "#3987e5", "#2a78d6", "#256abf", "#1c5cab",
              "#184f95", "#104281", "#0d366b")

SURFACE       <- "#fcfcfb"
INK           <- "#0b0b0b"
INK_SECONDARY <- "#52514e"
INK_MUTED     <- "#8a8880"
GRID          <- "#e5e4e0"

SPURS_COLOR <- "#2a78d6"
FIELD_COLOR <- "#b8b6ae"
HIGHLIGHT   <- "#eb6834"


#' Open a PNG device with the repository's defaults.
open_png <- function(path, width = 9, height = 5.6, res = 200) {
  png(path, width = width, height = height, units = "in", res = res,
      bg = SURFACE)
  par(
    family    = "sans",
    bg        = SURFACE,
    fg        = INK_SECONDARY,
    col.axis  = INK_SECONDARY,
    col.lab   = INK_SECONDARY,
    col.main  = INK,
    mar       = c(4.2, 4.6, 4.4, 1.4),
    mgp       = c(2.6, 0.6, 0),
    tcl       = 0,
    las       = 1,
    cex.axis  = 0.9,
    cex.lab   = 0.95,
    xaxs      = "r",
    yaxs      = "r"
  )
}


#' Left-aligned title block, matching the Python figures.
title_block <- function(title, subtitle = NULL) {
  mtext(title, side = 3, line = if (is.null(subtitle)) 1.2 else 2.4,
        adj = 0, cex = 1.15, font = 2, col = INK)
  if (!is.null(subtitle)) {
    mtext(subtitle, side = 3, line = 1.0, adj = 0, cex = 0.85,
          col = INK_SECONDARY)
  }
}


#' Recessive horizontal grid drawn behind the data.
add_grid <- function(h = TRUE, v = FALSE) {
  if (h) abline(h = axTicks(2), col = GRID, lwd = 0.9)
  if (v) abline(v = axTicks(1), col = GRID, lwd = 0.9)
}


#' Axes without tick marks or a box, so the data carries the chart.
clean_axes <- function(xlab = "", ylab = "", xat = NULL, yat = NULL,
                       xlabels = TRUE, ylabels = TRUE) {
  axis(1, at = xat, labels = xlabels, col = GRID, col.ticks = GRID,
       lwd = 0, lwd.ticks = 0)
  axis(2, at = yat, labels = ylabels, col = GRID, col.ticks = GRID,
       lwd = 0, lwd.ticks = 0)
  title(xlab = xlab, ylab = ylab)
}


#' Transparent version of a colour, for overplotted points.
alpha <- function(col, a = 0.5) {
  rgb_vals <- col2rgb(col) / 255
  rgb(rgb_vals[1], rgb_vals[2], rgb_vals[3], alpha = a)
}


#' Resolve a path relative to the repository root regardless of where the
#' script was launched from.
repo_path <- function(...) {
  root <- Sys.getenv("NBALAB_ROOT", unset = ".")
  file.path(root, ...)
}


#' Read one of the R-ready extracts written by tools/export_for_r.py.
read_extract <- function(name) {
  path <- repo_path("data", "r_extracts", paste0(name, ".csv"))
  if (!file.exists(path)) {
    stop(sprintf(
      "extract '%s' not found at %s -- run `python tools/export_for_r.py` first",
      name, path))
  }
  read.csv(path, stringsAsFactors = FALSE)
}


#' Coerce a column to logical regardless of how it was serialised.
#'
#' pandas writes booleans as the strings "True"/"False", which `read.csv`
#' loads as character; applying `!` to that raises "invalid argument type".
#' This accepts the Python spelling, the R spelling and 0/1.
as_logical <- function(x) {
  if (is.logical(x)) return(x)
  if (is.numeric(x)) return(x != 0)
  tolower(as.character(x)) %in% c("true", "t", "1", "yes")
}


#' Print a compact summary table, used instead of a package dependency.
show_table <- function(df, digits = 3, n = 12) {
  print(utils::head(
    as.data.frame(lapply(df, function(x)
      if (is.numeric(x)) round(x, digits) else x),
      stringsAsFactors = FALSE),
    n), row.names = FALSE)
}
