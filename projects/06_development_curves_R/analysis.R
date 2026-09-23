# Experience curves estimated from repeated player-season ratings.
source(file.path(Sys.getenv("NBALAB_ROOT", unset = "."), "Rlab", "theme.R"))
library(splines)

set.seed(2027)

FIG <- repo_path("projects", "06_development_curves_R", "figures")
dir.create(FIG, showWarnings = FALSE, recursive = TRUE)

MIN_MINUTES <- 500
N_BOOT      <- 400
SPURS_CORE  <- c("Victor Wembanyama", "Stephon Castle",
                 "Dylan Harper", "Carter Bryant")


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

ps <- read_extract("player_seasons")
ps$debut_censored <- as_logical(ps$debut_censored)
ps <- ps[!ps$debut_censored & !is.na(ps$minutes) & ps$minutes >= MIN_MINUTES, ]
ps <- ps[ps$experience >= 0 & ps$experience <= 16, ]

cat(sprintf("player-seasons after filtering: %d  (%d distinct players)\n",
            nrow(ps), length(unique(ps$player_id))))
cat(sprintf("experience range: %d to %d\n",
            min(ps$experience), max(ps$experience)))


# ---------------------------------------------------------------------------
# Estimator 1: the delta method
# ---------------------------------------------------------------------------

delta_method <- function(d) {
  d <- d[order(d$player_id, d$season), ]
  same   <- c(FALSE, d$player_id[-1] == d$player_id[-nrow(d)])
  consec <- c(FALSE, diff(d$season) == 1) & same

  from   <- d$experience[c(consec[-1], FALSE)]
  change <- diff(d$rapm)[consec[-1]]
  weight <- pmin(d$minutes[-nrow(d)], d$minutes[-1])[consec[-1]]

  ok <- !is.na(from) & !is.na(change) & !is.na(weight)
  from <- from[ok]; change <- change[ok]; weight <- weight[ok]

  steps <- tapply(seq_along(from), from, function(i)
    sum(change[i] * weight[i]) / sum(weight[i]))
  counts <- tapply(from, from, length)

  exp_levels <- as.integer(names(steps))
  data.frame(
    from       = exp_levels,
    step       = as.numeric(steps),
    n          = as.integer(counts),
    cumulative = cumsum(as.numeric(steps))
  )
}

deltas <- delta_method(ps)
cat("\nDelta method -- year-over-year change in RAPM by experience:\n")
show_table(deltas, n = 16)


# ---------------------------------------------------------------------------
# Estimator 2: player fixed effects with a spline
# ---------------------------------------------------------------------------

# The within transformation: subtract each player's own weighted mean from
# the response and from every basis column.  What remains identifies the
# experience profile using only within-player variation.
demean_by <- function(x, group, w) {
  means <- tapply(x * w, group, sum) / tapply(w, group, sum)
  x - means[as.character(group)]
}

fit_fixed_effects <- function(d, df_spline = 4) {
  basis <- ns(d$experience, df = df_spline)
  w <- d$minutes

  y <- demean_by(d$rapm, d$player_id, w)
  X <- apply(basis, 2, demean_by, group = d$player_id, w = w)

  fit <- lm.wfit(x = as.matrix(X), y = y, w = w)

  grid <- 0:16
  pred_basis <- predict(basis, newx = grid)
  curve <- as.vector(pred_basis %*% fit$coefficients)
  curve <- curve - curve[1]          # express relative to a rookie season

  list(fit = fit, basis = basis, curve = data.frame(
    experience = grid, effect = curve))
}

fe <- fit_fixed_effects(ps)
cat("\nFixed-effects spline -- RAPM relative to the rookie season:\n")
show_table(fe$curve, n = 17)


# ---------------------------------------------------------------------------
# Uncertainty: bootstrap over players
# ---------------------------------------------------------------------------

bootstrap_curve <- function(d, n_boot = N_BOOT, df_spline = 4) {
  players <- unique(d$player_id)
  grid <- 0:16
  out <- matrix(NA_real_, nrow = n_boot, ncol = length(grid))

  for (b in seq_len(n_boot)) {
    picked <- sample(players, length(players), replace = TRUE)
    idx <- unlist(lapply(picked, function(p) which(d$player_id == p)))
    boot <- d[idx, ]
    # Resampled players must stay distinguishable, or the within
    # transformation would pool duplicate draws of the same player.
    boot$player_id <- rep(seq_along(picked),
                          times = vapply(picked, function(p)
                            sum(d$player_id == p), integer(1)))
    res <- try(fit_fixed_effects(boot, df_spline), silent = TRUE)
    if (!inherits(res, "try-error")) out[b, ] <- res$curve$effect
  }
  out
}

cat(sprintf("\nbootstrapping %d player-level resamples ...\n", N_BOOT))
boot <- bootstrap_curve(ps)
ok <- rowSums(is.na(boot)) == 0
boot <- boot[ok, , drop = FALSE]
cat(sprintf("  %d of %d resamples converged\n", nrow(boot), N_BOOT))

ci <- t(apply(boot, 2, quantile, probs = c(0.10, 0.90), na.rm = TRUE))
fe$curve$lo <- ci[, 1]
fe$curve$hi <- ci[, 2]


# ---------------------------------------------------------------------------
# Projecting the Spurs core
# ---------------------------------------------------------------------------

latest <- ps[ps$season == 2025, ]
core <- latest[latest$player_name %in% SPURS_CORE, ]

step_from <- function(e) {
  a <- fe$curve$effect[fe$curve$experience == e]
  b <- fe$curve$effect[fe$curve$experience == e + 1]
  if (length(a) == 0 || length(b) == 0) return(0)
  b - a
}
step_ci <- function(e) {
  i <- which(fe$curve$experience == e)
  j <- which(fe$curve$experience == e + 1)
  d <- boot[, j] - boot[, i]
  quantile(d, probs = c(0.10, 0.90), na.rm = TRUE)
}

if (nrow(core) > 0) {
  core$expected_step <- vapply(core$experience, step_from, numeric(1))
  bounds <- t(vapply(core$experience, step_ci, numeric(2)))
  core$step_lo <- bounds[, 1]
  core$step_hi <- bounds[, 2]
  core$projected_rapm <- core$rapm + core$expected_step

  cat("\nProjected 2026-27 RAPM for the young core:\n")
  show_table(core[order(-core$projected_rapm),
                  c("player_name", "experience", "minutes", "rapm",
                    "expected_step", "step_lo", "step_hi", "projected_rapm")],
             n = 10)
}


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------

open_png(file.path(FIG, "development_curve.png"), width = 9.5, height = 5.8)
xr <- c(0, 16)
yr <- range(c(fe$curve$lo, fe$curve$hi, deltas$cumulative), na.rm = TRUE)
yr <- yr + c(-0.15, 0.25) * diff(yr)

plot(NA, xlim = xr, ylim = yr, axes = FALSE, xlab = "", ylab = "")
add_grid()
abline(h = 0, col = INK_SECONDARY, lwd = 1.1)

polygon(c(fe$curve$experience, rev(fe$curve$experience)),
        c(fe$curve$lo, rev(fe$curve$hi)),
        col = alpha(PALETTE["blue"], 0.16), border = NA)
lines(fe$curve$experience, fe$curve$effect, col = PALETTE["blue"], lwd = 2.6)
lines(deltas$from + 1, deltas$cumulative, col = PALETTE["orange"], lwd = 2.2,
      lty = 2)

clean_axes(xlab = "Seasons of NBA experience",
           ylab = "RAPM relative to the rookie season")
legend("topright", bty = "n", lwd = c(2.6, 2.2), lty = c(1, 2),
       col = c(PALETTE["blue"], PALETTE["orange"]),
       legend = c("Player fixed effects (80% interval)", "Delta method"),
       text.col = INK_SECONDARY)
title_block(
  "Two estimates of the mean experience profile",
  sprintf("%d player-seasons, %d players, minimum %d minutes  |  fixed effects fitted by the within transformation",
          nrow(ps), length(unique(ps$player_id)), MIN_MINUTES))
dev.off()


if (nrow(core) > 0) {
  open_png(file.path(FIG, "spurs_core_projection.png"), width = 9, height = 5.4)
  par(mar = c(4.2, 11.2, 4.6, 1.4))
  core <- core[order(core$rapm), ]
  n <- nrow(core)
  ylim <- c(0.5, n + 0.5)
  xr <- range(c(core$rapm, core$rapm + core$step_hi,
                core$rapm + core$step_lo))
  xr <- xr + c(-0.25, 0.45) * diff(xr)

  plot(NA, xlim = xr, ylim = ylim, axes = FALSE, xlab = "", ylab = "")
  add_grid(h = FALSE, v = TRUE)
  abline(v = 0, col = INK_SECONDARY, lwd = 1.1)

  for (i in seq_len(n)) {
    segments(core$rapm[i], i, core$projected_rapm[i], i,
             col = GRID, lwd = 5, lend = 1)
    segments(core$rapm[i] + core$step_lo[i], i,
             core$rapm[i] + core$step_hi[i], i,
             col = alpha(PALETTE["orange"], 0.45), lwd = 5, lend = 1)
  }
  points(core$rapm, seq_len(n), pch = 19, col = FIELD_COLOR, cex = 1.5)
  points(core$projected_rapm, seq_len(n), pch = 19,
         col = PALETTE["orange"], cex = 1.7)

  axis(2, at = seq_len(n), labels = core$player_name, col = GRID,
       lwd = 0, lwd.ticks = 0, cex.axis = 0.92)
  axis(1, col = GRID, lwd = 0, lwd.ticks = 0)
  title(xlab = "RAPM (points per 100 possessions)")
  legend("bottomright", bty = "n", pch = 19, pt.cex = c(1.5, 1.7),
         col = c(FIELD_COLOR, PALETTE["orange"]),
         legend = c("2025-26 actual", "Mean-step scenario (80% interval)"),
         text.col = INK_SECONDARY)
  title_block("Mean experience steps applied to the Spurs core",
              "Projection applies the fitted development step for each player's experience level")
  dev.off()
}


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

out_dir <- repo_path("projects", "06_development_curves_R")
write.csv(fe$curve, file.path(out_dir, "development_curve.csv"), row.names = FALSE)
write.csv(deltas, file.path(out_dir, "delta_method.csv"), row.names = FALSE)
if (nrow(core) > 0) {
  write.csv(core[, c("player_name", "experience", "minutes", "rapm",
                     "expected_step", "step_lo", "step_hi", "projected_rapm")],
            file.path(out_dir, "spurs_core_projection.csv"), row.names = FALSE)
}

cat("\ncorrelation between the two estimators over experience 1-12: ")
cmp <- merge(fe$curve, data.frame(experience = deltas$from + 1,
                                  cumulative = deltas$cumulative),
             by = "experience")
cmp <- cmp[cmp$experience <= 12, ]
cat(sprintf("%.3f\n", cor(cmp$effect, cmp$cumulative)))
cat("\nwrote 2 figures and 3 tables to", out_dir, "\n")
