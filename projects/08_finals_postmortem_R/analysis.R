# Game and quarter scoring with a within-game stint resampling sensitivity check.
source(file.path(Sys.getenv("NBALAB_ROOT", unset = "."), "Rlab", "theme.R"))

set.seed(2026)

FIG <- repo_path("projects", "08_finals_postmortem_R", "figures")
dir.create(FIG, showWarnings = FALSE, recursive = TRUE)

WEMBY_NAME <- "Victor Wembanyama"


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

stints <- read_extract("finals_stints")
shots  <- read_extract("finals_shots")
shots$is_spurs <- as_logical(shots$is_spurs)
shots$is_three <- as_logical(shots$is_three)

games <- sort(unique(stints$game_number))
cat(sprintf("2026 Finals: %d games reconstructed (%s)\n",
            length(games), paste0("G", games, collapse = " ")))


# ---------------------------------------------------------------------------
# Where the series went
# ---------------------------------------------------------------------------

by_game <- aggregate(cbind(spurs_points, opp_points, team_possessions, seconds) ~
                       game_number, data = stints, FUN = sum)
by_game$margin <- by_game$spurs_points - by_game$opp_points
by_game$off_rating <- 100 * by_game$spurs_points / by_game$team_possessions
by_game$def_rating <- 100 * by_game$opp_points / by_game$team_possessions
by_game$net_rating <- by_game$off_rating - by_game$def_rating
by_game$result <- ifelse(by_game$margin > 0, "W", "L")

cat("\nGame by game:\n")
show_table(by_game[, c("game_number", "result", "spurs_points", "opp_points",
                       "margin", "off_rating", "def_rating", "net_rating")],
           n = 7)

cat(sprintf("\nseries margin: %+d points over %d games (%.1f per game)\n",
            sum(by_game$margin), nrow(by_game), mean(by_game$margin)))
cat(sprintf("games decided by 4 points or fewer: %d of %d\n",
            sum(abs(by_game$margin) <= 4), nrow(by_game)))


by_quarter <- aggregate(cbind(spurs_points, opp_points, team_possessions) ~
                          period, data = stints, FUN = sum)
by_quarter$margin <- by_quarter$spurs_points - by_quarter$opp_points
by_quarter$net_rating <- 100 * by_quarter$margin / by_quarter$team_possessions

cat("\nBy quarter, across the series:\n")
show_table(by_quarter[, c("period", "spurs_points", "opp_points", "margin",
                          "net_rating")], n = 6)


# ---------------------------------------------------------------------------
# Shot mix: worse shots, or the same shots missed?
# ---------------------------------------------------------------------------

spurs_shots <- shots[shots$is_spurs, ]

mix <- table(spurs_shots$game_number, spurs_shots$zone)
mix_share <- prop.table(mix, margin = 1)

made <- tapply(spurs_shots$shot_made_flag, spurs_shots$zone, mean)
attempts <- table(spurs_shots$zone)

cat("\nSpurs shooting by zone across the series:\n")
zone_tbl <- data.frame(
  zone = names(attempts),
  attempts = as.integer(attempts),
  fg_pct = as.numeric(made[names(attempts)])
)
show_table(zone_tbl[order(-zone_tbl$attempts), ], n = 6)

# Effective field goal percentage per game.
efg_by_game <- sapply(games, function(g) {
  s <- spurs_shots[spurs_shots$game_number == g, ]
  (sum(s$shot_made_flag) + 0.5 * sum(s$shot_made_flag & s$is_three)) / nrow(s)
})
opp_shots <- shots[!shots$is_spurs, ]
opp_efg_by_game <- sapply(games, function(g) {
  s <- opp_shots[opp_shots$game_number == g, ]
  (sum(s$shot_made_flag) + 0.5 * sum(s$shot_made_flag & s$is_three)) / nrow(s)
})

cat("\nEffective field goal percentage by game:\n")
show_table(data.frame(game = games, spurs_efg = efg_by_game,
                      knicks_efg = opp_efg_by_game,
                      gap = efg_by_game - opp_efg_by_game), n = 7)


# ---------------------------------------------------------------------------
# Wembanyama's arc
# ---------------------------------------------------------------------------

wemby <- spurs_shots[spurs_shots$player_name == WEMBY_NAME, ]
wemby_by_game <- data.frame(
  game = games,
  attempts = sapply(games, function(g) sum(wemby$game_number == g)),
  makes = sapply(games, function(g) sum(wemby$shot_made_flag[wemby$game_number == g])),
  points = sapply(games, function(g) sum(wemby$shot_made_flag[wemby$game_number == g] *
                                           wemby$points_if_made[wemby$game_number == g])),
  rim_share = sapply(games, function(g) {
    s <- wemby[wemby$game_number == g, ]
    if (nrow(s) == 0) NA_real_ else mean(s$zone == "rim")
  }),
  avg_distance = sapply(games, function(g) {
    s <- wemby[wemby$game_number == g, ]
    if (nrow(s) == 0) NA_real_ else mean(s$shot_distance)
  })
)
wemby_by_game$fg_pct <- wemby_by_game$makes / wemby_by_game$attempts

cat("\nWembanyama, game by game (field goals only -- free throws are not in this extract):\n")
show_table(wemby_by_game, n = 7)


# ---------------------------------------------------------------------------
# Resample stints within each game; this changes frequencies and playing time.
# The exercise is conditional on observed games and is not a series-win model.

resample_series <- function(n_rep = 20000) {
  wins <- integer(n_rep)
  per_game <- split(stints, stints$game_number)
  for (r in seq_len(n_rep)) {
    w <- 0
    for (g in per_game) {
      idx <- sample(seq_len(nrow(g)), nrow(g), replace = TRUE)
      margin <- sum(g$spurs_points[idx]) - sum(g$opp_points[idx])
      if (margin > 0 || (margin == 0 && runif(1) < 0.5)) w <- w + 1
    }
    wins[r] <- w
  }
  wins
}

cat("\nresampling the five games 20,000 times ...\n")
sim_wins <- resample_series()
tab <- table(factor(sim_wins, levels = 0:5))
cat("\ndistribution of Spurs wins in the five games actually played:\n")
show_table(data.frame(spurs_wins = 0:5,
                      probability = as.numeric(tab) / length(sim_wins)), n = 6)
cat(sprintf("\nresample frequency with three or more Spurs game wins: %.1f%%\n",
            100 * mean(sim_wins >= 3)))


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------

open_png(file.path(FIG, "series_margins.png"), width = 9.5, height = 5.4)
cols <- ifelse(by_game$margin > 0, PALETTE["blue"], PALETTE["orange"])
ylim <- c(min(by_game$margin) - 3, max(by_game$margin) + 4)
bp <- barplot(by_game$margin, col = cols, border = NA, ylim = ylim,
              names.arg = paste0("Game ", by_game$game_number),
              axes = FALSE, space = 0.45)
add_grid()
abline(h = 0, col = INK_SECONDARY, lwd = 1.2)
barplot(by_game$margin, col = cols, border = NA, add = TRUE, axes = FALSE,
        names.arg = rep("", nrow(by_game)), space = 0.45)
axis(2, col = GRID, lwd = 0, lwd.ticks = 0)
text(bp, by_game$margin + ifelse(by_game$margin > 0, 1.2, -1.6),
     labels = sprintf("%+d", by_game$margin), cex = 0.9, col = INK_SECONDARY)
title(ylab = "San Antonio's margin (points)")
title_block("A 4-1 series decided by six points across three games",
            sprintf("Series point margin %+d over five games | %d of 5 games decided by four points or fewer",
                    sum(by_game$margin), sum(abs(by_game$margin) <= 4)))
dev.off()


open_png(file.path(FIG, "quarter_margins.png"), width = 9.5, height = 5.2)
qcols <- ifelse(by_quarter$margin > 0, PALETTE["blue"], PALETTE["orange"])
ylim <- c(min(by_quarter$margin) - 3, max(by_quarter$margin) + 4)
bp <- barplot(by_quarter$margin, col = qcols, border = NA, ylim = ylim,
              names.arg = paste0("Q", by_quarter$period), axes = FALSE,
              space = 0.5)
add_grid()
abline(h = 0, col = INK_SECONDARY, lwd = 1.2)
barplot(by_quarter$margin, col = qcols, border = NA, add = TRUE, axes = FALSE,
        names.arg = rep("", nrow(by_quarter)), space = 0.5)
axis(2, col = GRID, lwd = 0, lwd.ticks = 0)
text(bp, by_quarter$margin + ifelse(by_quarter$margin > 0, 1.2, -1.6),
     labels = sprintf("%+d", by_quarter$margin), cex = 0.9, col = INK_SECONDARY)
title(ylab = "Cumulative margin across the series (points)")
title_block("Quarter-by-quarter margin across the series",
            "San Antonio's total point margin by period, all five games combined")
dev.off()


open_png(file.path(FIG, "efg_by_game.png"), width = 9.5, height = 5.4)
yr <- range(c(efg_by_game, opp_efg_by_game)) + c(-0.04, 0.05)
plot(NA, xlim = c(0.7, length(games) + 0.3), ylim = yr, axes = FALSE,
     xlab = "", ylab = "")
add_grid()
lines(seq_along(games), efg_by_game, col = HIGHLIGHT, lwd = 2.6)
points(seq_along(games), efg_by_game, pch = 19, col = HIGHLIGHT, cex = 1.5)
lines(seq_along(games), opp_efg_by_game, col = FIELD_COLOR, lwd = 2.6)
points(seq_along(games), opp_efg_by_game, pch = 19, col = FIELD_COLOR, cex = 1.5)
clean_axes(xlab = "", ylab = "Effective field goal percentage",
           xat = seq_along(games), xlabels = paste0("Game ", games))
legend("topright", bty = "n", lwd = 2.6, pch = 19,
       col = c(HIGHLIGHT, FIELD_COLOR),
       legend = c("San Antonio", "New York"), text.col = INK_SECONDARY)
title_block("Shot making, game by game",
            "Effective field goal percentage counts a three as 1.5 field goals")
dev.off()


open_png(file.path(FIG, "wemby_series.png"), width = 9.5, height = 5.4)
par(mar = c(4.2, 4.8, 4.6, 4.6))
yr <- c(0, max(wemby_by_game$attempts) + 4)
bp <- barplot(wemby_by_game$attempts, col = alpha(FIELD_COLOR, 0.9), border = NA,
              ylim = yr, names.arg = paste0("Game ", wemby_by_game$game),
              axes = FALSE, space = 0.5)
axis(2, col = GRID, lwd = 0, lwd.ticks = 0)
title(ylab = "Field goal attempts")
text(bp, wemby_by_game$attempts + 1.2,
     labels = sprintf("%d pts", wemby_by_game$points), cex = 0.85,
     col = INK_SECONDARY)

# Field goal percentage on its own scale, drawn as a labelled overlay rather
# than a second axis with its own gridlines.
scaled <- wemby_by_game$fg_pct * max(yr) * 0.9
lines(bp, scaled, col = HIGHLIGHT, lwd = 2.6)
points(bp, scaled, pch = 19, col = HIGHLIGHT, cex = 1.5)
text(bp, scaled + 1.6, labels = sprintf("%.0f%%", 100 * wemby_by_game$fg_pct),
     cex = 0.82, col = HIGHLIGHT)
title_block("Wembanyama's Finals",
            "Bars are field goal attempts, labelled with points from the field | the line is field goal percentage")
dev.off()


open_png(file.path(FIG, "series_resample.png"), width = 9.5, height = 5.2)
probs <- as.numeric(tab) / length(sim_wins)
bcols <- rep(FIELD_COLOR, 6)
bcols[2] <- HIGHLIGHT              # the 1 win that actually happened
bp <- barplot(probs, col = bcols, border = NA, names.arg = 0:5, axes = FALSE,
              ylim = c(0, max(probs) * 1.22), space = 0.45)
add_grid()
barplot(probs, col = bcols, border = NA, add = TRUE, axes = FALSE,
        names.arg = rep("", 6), space = 0.45)
axis(2, col = GRID, lwd = 0, lwd.ticks = 0)
text(bp, probs + max(probs) * 0.04, labels = sprintf("%.0f%%", 100 * probs),
     cex = 0.85, col = INK_SECONDARY)
title(xlab = "San Antonio wins in the five games played",
      ylab = "Probability")
title_block("Sensitivity to within-game stint resampling",
            "Stints sampled with replacement within each game; frequencies and playing time change")
dev.off()


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

out_dir <- repo_path("projects", "08_finals_postmortem_R")
write.csv(by_game, file.path(out_dir, "game_summary.csv"), row.names = FALSE)
write.csv(by_quarter, file.path(out_dir, "quarter_summary.csv"), row.names = FALSE)
write.csv(wemby_by_game, file.path(out_dir, "wembanyama_series.csv"), row.names = FALSE)
write.csv(data.frame(spurs_wins = 0:5, probability = probs),
          file.path(out_dir, "series_resample.csv"), row.names = FALSE)

cat("\nwrote 5 figures and 4 tables to", out_dir, "\n")
