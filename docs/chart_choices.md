# Chart choices (for the report and the presentation)

Why each view on the dashboard uses the chart type it does. The on-screen title and reading line come
from the same source, `src/dashboard/explain.py`.

| View | Question it answers | Chart type | Why this chart |
|---|---|---|---|
| At a glance (left) | How have prices changed over time? | Line chart · change over time | A line is the clearest way to show how a value moves month by month and to compare a few categories on one scale. Brief F3: change over time. |
| At a glance (right) | How do the categories compare? | Bar chart · comparison between categories | Bars of the same width are compared by length, which people read more accurately than angles or colours. Brief F3: comparison between categories. |
| Spending & drivers (left) | What do households spend their money on? | Bar chart · composition | With 12 groups, a sorted bar chart shows the shares far more clearly than a pie chart. Brief F3: composition. |
| Spending & drivers (right) | What pushed overall prices up or down? | Bar chart · contribution to inflation | A category matters by how much it changed AND how much households spend on it. This chart combines the two, so it explains the headline figure. |
| Months & years (top) | Which months saw the biggest changes? (with *Price level* chosen: How high were prices, month by month?) | Heat map · distribution across categories and months | A heat map shows many months and categories at once, so patterns such as a seasonal rise or one unusual month stand out. Red = above the reference (no change, or April 2019 = 100), blue = below, grey = about the same; the line under the title changes with the measure. Brief F3: distribution. |
| Months & years (below) | How did whole years compare? | Table · annual averages | Replies often compare this year with earlier ones; the average of all 12 months smooths out single months, and a year is shown only when all 12 months are published. A table gives the exact figures to quote. Proposal: comparisons between periods, including annual averages. |

Other views: four key-number cards (each with a plain-language sentence and the name of the measure),
an "In plain words" summary generated from the data, a table of every selected category with a CSV
download, and the monitoring-priorities table with a plain reason for each spending group.
