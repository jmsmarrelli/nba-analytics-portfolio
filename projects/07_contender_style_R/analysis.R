# Project 07 -- the style space of the 2026-27 contender field
#
# Every contender is good, but they are not good in the same way.  Playoff
# series are matchup problems, and matchups are about *style* -- how fast a
# team plays, where its shots come from -- rather than about who is better in
# the abstract.
#
# This project builds a style space from shot-location and tempo features
# only, deliberately excluding efficiency, so that two teams sitting close
# together are playing the same way regardless of how well.  Principal
# components compress it to two readable dimensions; hierarchical clustering
# cuts the field into stylistic families; and the same projection applied to
# seven seasons shows where the league as a whole has drifted and whether
# San Antonio moved with it.
#
# Base R only -- stats, graphics.

source(file.path(Sys.getenv("NBALAB_ROOT", unset = "."), "Rlab", "theme.R"))

FIG <- repo_path("projects", "07_contender_style_R", "figures")
dir.create(FIG, showWarnings = FALSE, recursive = TRUE)

SEASON     <- 2025
CONTENDERS <- c("SAS", "OKC", "NYK", "BOS", "DET", "HOU", "CLE", "DEN", "MIN")

# Style features only.  Efficiency is held out so the space describes *how* a
# team plays, not how well -- otherwise the first component is just quality
# and the picture says nothing a standings table would not.
STYLE_VARS <- c("pace", "rim_rate", "short_mid_rate", "long_mid_rate",
                "three_rate", "corner_three_share", "avg_shot_distance")

PRETTY <- c(pace = "Pace", rim_rate = "Rim rate",
            short_mid_rate = "Short mid-range", long_mid_rate = "Long mid-range",
            three_rate = "Three-point rate", corner_three_share = "Corner-three share",
            avg_shot_distance = "Average shot distance")


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

style <- read_extract("team_style")
style <- style[!is.na(style$pace), ]
cur <- style[style$season == SEASON, ]
rownames(cur) <- cur$tricode

cat(sprintf("teams in %d-%02d: %d   seasons available: %s\n",
            SEASON, (SEASON + 1) %% 100, nrow(cur),
            paste(range(style$season), collapse = "-")))


# ---------------------------------------------------------------------------
# Principal components
# ---------------------------------------------------------------------------

X <- as.matrix(cur[, STYLE_VARS])
pca <- prcomp(X, center = TRUE, scale. = TRUE)

var_share <- pca$sdev^2 / sum(pca$sdev^2)
cat(sprintf("\nvariance explained: PC1 %.1f%%, PC2 %.1f%%, PC3 %.1f%% (cumulative %.1f%%)\n",
            100 * var_share[1], 100 * var_share[2], 100 * var_share[3],
            100 * sum(var_share[1:3])))

cat("\nloadings (what each component actually measures):\n")
load_tbl <- data.frame(
  feature = PRETTY[STYLE_VARS],
  PC1 = round(pca$rotation[, 1], 3),
  PC2 = round(pca$rotation[, 2], 3)
)
print(load_tbl[order(-abs(load_tbl$PC1)), ], row.names = FALSE)

scores <- as.data.frame(pca$x[, 1:3])
scores$tricode <- cur$tricode
scores$net_rating <- cur$net_rating
scores$wins <- cur$wins


# ---------------------------------------------------------------------------
# Stylistic families
# ---------------------------------------------------------------------------

d <- dist(scale(X))
hc <- hclust(d, method = "ward.D2")
k <- 4
scores$cluster <- cutree(hc, k = k)

cat(sprintf("\nfour stylistic families (Ward linkage on standardised style features):\n"))
for (g in seq_len(k)) {
  members <- scores$tricode[scores$cluster == g]
  centre <- colMeans(cur[cur$tricode %in% members, STYLE_VARS, drop = FALSE])
  cat(sprintf("\n  cluster %d (%d teams): %s\n", g, length(members),
              paste(members, collapse = " ")))
  cat(sprintf("    pace %.1f | rim %.1f%% | short mid %.1f%% | long mid %.1f%% | three %.1f%%\n",
              centre["pace"], 100 * centre["rim_rate"],
              100 * centre["short_mid_rate"], 100 * centre["long_mid_rate"],
              100 * centre["three_rate"]))
}


# ---------------------------------------------------------------------------
# Who does San Antonio look like?
# ---------------------------------------------------------------------------

sas <- scores[scores$tricode == "SAS", c("PC1", "PC2", "PC3")]
dists <- sqrt(rowSums((scores[, c("PC1", "PC2", "PC3")] -
                       matrix(as.numeric(sas), nrow(scores), 3, byrow = TRUE))^2))
neighbours <- data.frame(tricode = scores$tricode, distance = dists,
                         net_rating = scores$net_rating)
neighbours <- neighbours[order(neighbours$distance), ][-1, ]
cat("\nclosest stylistic neighbours to San Antonio:\n")
show_table(head(neighbours, 6), n = 6)

cat("\nmost stylistically distant from San Antonio:\n")
show_table(tail(neighbours, 4), n = 4)


# ---------------------------------------------------------------------------
# League drift, seven seasons
# ---------------------------------------------------------------------------

all_scores <- predict(pca, newdata = as.matrix(style[, STYLE_VARS]))
style$PC1 <- all_scores[, 1]
style$PC2 <- all_scores[, 2]

drift <- aggregate(cbind(PC1, PC2) ~ season, data = style, FUN = mean)
cat("\nleague-average position in the style space by season:\n")
show_table(drift, n = 10)

spurs_path <- style[style$tricode == "SAS", c("season", "PC1", "PC2")]
spurs_path <- spurs_path[order(spurs_path$season), ]


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------

cluster_cols <- unname(PALETTE[c("blue", "orange", "aqua", "violet")])

open_png(file.path(FIG, "style_space.png"), width = 9.5, height = 7.6)
xr <- range(scores$PC1) + c(-0.55, 0.75)
yr <- range(scores$PC2) + c(-0.5, 0.6)
plot(NA, xlim = xr, ylim = yr, axes = FALSE, xlab = "", ylab = "")
add_grid(h = TRUE, v = TRUE)
abline(h = 0, v = 0, col = GRID, lwd = 1.2)

is_cont <- scores$tricode %in% CONTENDERS
is_sas  <- scores$tricode == "SAS"

points(scores$PC1[!is_cont], scores$PC2[!is_cont], pch = 19,
       col = alpha(FIELD_COLOR, 0.75), cex = 1.15)
points(scores$PC1[is_cont & !is_sas], scores$PC2[is_cont & !is_sas], pch = 19,
       col = cluster_cols[scores$cluster[is_cont & !is_sas]], cex = 1.9)
points(scores$PC1[is_sas], scores$PC2[is_sas], pch = 19,
       col = HIGHLIGHT, cex = 2.7)

text(scores$PC1[is_cont], scores$PC2[is_cont], labels = scores$tricode[is_cont],
     pos = 4, offset = 0.55, cex = 0.82,
     col = ifelse(scores$tricode[is_cont] == "SAS", HIGHLIGHT, INK_SECONDARY),
     font = ifelse(scores$tricode[is_cont] == "SAS", 2, 1))

# Loading arrows, scaled to the plot.
arrow_scale <- 0.75 * min(diff(xr), diff(yr))
for (v in STYLE_VARS) {
  ax <- pca$rotation[v, 1] * arrow_scale
  ay <- pca$rotation[v, 2] * arrow_scale
  arrows(0, 0, ax, ay, length = 0.07, col = alpha(INK_MUTED, 0.85), lwd = 1.1)
  text(ax * 1.1, ay * 1.1, PRETTY[v], cex = 0.68, col = INK_MUTED,
       adj = c(if (ax > 0) 0 else 1, 0.5))
}

clean_axes(
  xlab = sprintf("PC1 (%.0f%% of variance)", 100 * var_share[1]),
  ylab = sprintf("PC2 (%.0f%% of variance)", 100 * var_share[2]))
title_block("How the contenders actually play",
            sprintf("%d-%02d shot location and tempo only -- efficiency excluded, so distance means stylistic difference | colour marks the clustered family",
                    SEASON, (SEASON + 1) %% 100))
dev.off()


open_png(file.path(FIG, "league_drift.png"), width = 9.5, height = 6)
xr <- range(style$PC1); yr <- range(style$PC2)
plot(NA, xlim = xr, ylim = yr, axes = FALSE, xlab = "", ylab = "")
add_grid(h = TRUE, v = TRUE)
points(style$PC1, style$PC2, pch = 19, col = alpha(FIELD_COLOR, 0.35), cex = 0.8)

lines(drift$PC1, drift$PC2, col = PALETTE["blue"], lwd = 2.6)
points(drift$PC1, drift$PC2, pch = 19, col = PALETTE["blue"], cex = 1.5)
text(drift$PC1, drift$PC2, labels = substr(drift$season, 3, 4), pos = 3,
     cex = 0.72, col = PALETTE["blue"])

lines(spurs_path$PC1, spurs_path$PC2, col = HIGHLIGHT, lwd = 2.4, lty = 2)
points(spurs_path$PC1, spurs_path$PC2, pch = 19, col = HIGHLIGHT, cex = 1.4)
text(spurs_path$PC1[nrow(spurs_path)], spurs_path$PC2[nrow(spurs_path)],
     labels = "SAS", pos = 4, cex = 0.85, col = HIGHLIGHT, font = 2)

clean_axes(xlab = sprintf("PC1 (%.0f%% of variance)", 100 * var_share[1]),
           ylab = sprintf("PC2 (%.0f%% of variance)", 100 * var_share[2]))
legend("topleft", bty = "n", lwd = c(2.6, 2.4), lty = c(1, 2),
       col = c(PALETTE["blue"], HIGHLIGHT),
       legend = c("League average, 2019-20 to 2025-26", "San Antonio"),
       text.col = INK_SECONDARY)
title_block("Seven seasons of stylistic drift",
            "Every team-season projected into the same space | grey points are individual team-seasons")
dev.off()


open_png(file.path(FIG, "style_dendrogram.png"), width = 9.5, height = 5.6)
par(mar = c(4.5, 4.4, 4.4, 1.2))
labels_col <- ifelse(cur$tricode == "SAS", HIGHLIGHT,
                     ifelse(cur$tricode %in% CONTENDERS, INK, INK_MUTED))
plot(hc, main = "", sub = "", xlab = "", ylab = "Ward linkage distance",
     hang = -1, cex = 0.78, col = INK_SECONDARY, axes = FALSE, labels = cur$tricode)
axis(2, col = GRID, lwd = 0, lwd.ticks = 0)
rect.hclust(hc, k = k, border = cluster_cols)
title_block("Stylistic families in the 2025-26 league",
            "Ward linkage on standardised tempo and shot-location features")
dev.off()


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

out_dir <- repo_path("projects", "07_contender_style_R")
write.csv(scores, file.path(out_dir, "style_scores.csv"), row.names = FALSE)
write.csv(load_tbl, file.path(out_dir, "pca_loadings.csv"), row.names = FALSE)
write.csv(neighbours, file.path(out_dir, "spurs_style_neighbours.csv"),
          row.names = FALSE)

cat("\nwrote 3 figures and 3 tables to", out_dir, "\n")
