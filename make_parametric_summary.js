const pptxgen = require("pptxgenjs");

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9";
pres.title = "Parametric Study Summary";

const slide = pres.addSlide();
slide.background = { color: "F5F5F7" };

const makeShadow = () => ({ type: "outer", blur: 8, offset: 2, angle: 135, color: "000000", opacity: 0.08 });

// Title
slide.addText("Parametric Study — Key Findings", {
  x: 0.4, y: 0.22, w: 9.2, h: 0.48,
  fontSize: 26, bold: true, color: "1D1D1F",
  fontFace: "Cambria", margin: 0
});

// Subtitle
slide.addText("Three stress tests. System held in every case.", {
  x: 0.4, y: 0.68, w: 9.2, h: 0.28,
  fontSize: 12, color: "6E6E73", fontFace: "Calibri", margin: 0
});

const CARD_Y = 1.08;
const CARD_H = 3.55;
const CARD_W = 2.97;
const GAP = 0.145;
const ACCENT_W = 0.1;

const cards = [
  {
    x: 0.4,
    accent: "FF3B30",
    statBg: "FFF2F2",
    statColor: "FF3B30",
    statLabelColor: "A2220F",
    pillText: "Task completed",
    title: "Hardware fault",
    sub: "Locked right knee",
    whatChanged: "Speed reduced, rightward drift introduced",
    stats: [{ val: "+22%", label: "time to goal" }, { val: "+51%", label: "wall collisions" }],
    twoStats: true,
  },
  {
    x: 0.4 + CARD_W + GAP,
    accent: "FF9500",
    statBg: "FFF8EC",
    statColor: "FF9500",
    statLabelColor: "7D4700",
    pillText: "No replanning, no collisions",
    title: "Dynamic obstacle",
    sub: "Sliding barrier, SEED 42",
    whatChanged: "Corridor temporarily blocked every 18 s",
    stats: [{ val: "+6.3 s", label: "total delay added" }],
    twoStats: false,
  },
  {
    x: 0.4 + 2 * (CARD_W + GAP),
    accent: "30B0C7",
    statBg: "EBF8FB",
    statColor: "0B7A8A",
    statLabelColor: "0B5E6B",
    pillText: "Non-uniform cost map favours Dijkstra",
    title: "Path planning",
    sub: "Dijkstra vs. A*",
    whatChanged: "Planner algorithm swapped across maze sizes",
    stats: [{ val: "~25% faster", label: "Dijkstra vs. A*" }],
    twoStats: false,
  },
];

for (const c of cards) {
  // Card background
  slide.addShape(pres.shapes.RECTANGLE, {
    x: c.x, y: CARD_Y, w: CARD_W, h: CARD_H,
    fill: { color: "FFFFFF" },
    line: { color: "D1D1D6", width: 0.5 },
    shadow: makeShadow(),
  });

  // Accent bar
  slide.addShape(pres.shapes.RECTANGLE, {
    x: c.x, y: CARD_Y, w: ACCENT_W, h: CARD_H,
    fill: { color: c.accent },
    line: { color: c.accent, width: 0 },
  });

  const tx = c.x + 0.2;
  const tw = CARD_W - 0.28;

  // Card title
  slide.addText(c.title, {
    x: tx, y: CARD_Y + 0.14, w: tw, h: 0.26,
    fontSize: 12, bold: true, color: "1D1D1F",
    fontFace: "Calibri", margin: 0,
  });

  // Card subtitle
  slide.addText(c.sub, {
    x: tx, y: CARD_Y + 0.40, w: tw, h: 0.22,
    fontSize: 10, color: "6E6E73",
    fontFace: "Calibri", margin: 0,
  });

  // Divider
  slide.addShape(pres.shapes.LINE, {
    x: tx, y: CARD_Y + 0.68, w: tw, h: 0,
    line: { color: "E5E5EA", width: 0.5 },
  });

  // "WHAT CHANGED" label
  slide.addText("WHAT CHANGED", {
    x: tx, y: CARD_Y + 0.76, w: tw, h: 0.18,
    fontSize: 8, bold: true, color: "6E6E73",
    fontFace: "Calibri", charSpacing: 0.5, margin: 0,
  });

  // Description
  slide.addText(c.whatChanged, {
    x: tx, y: CARD_Y + 0.96, w: tw, h: 0.36,
    fontSize: 10.5, color: "1D1D1F",
    fontFace: "Calibri", margin: 0,
  });

  // "KEY FINDING" label
  slide.addText("KEY FINDING", {
    x: tx, y: CARD_Y + 1.44, w: tw, h: 0.18,
    fontSize: 8, bold: true, color: "6E6E73",
    fontFace: "Calibri", charSpacing: 0.5, margin: 0,
  });

  if (c.twoStats) {
    const sw = (tw - 0.08) / 2;
    for (let i = 0; i < 2; i++) {
      const sx = tx + i * (sw + 0.08);
      slide.addShape(pres.shapes.RECTANGLE, {
        x: sx, y: CARD_Y + 1.68, w: sw, h: 0.72,
        fill: { color: c.statBg },
        line: { color: c.statBg, width: 0 },
      });
      slide.addText(c.stats[i].val, {
        x: sx, y: CARD_Y + 1.76, w: sw, h: 0.32,
        fontSize: 16, bold: true, color: c.statColor,
        fontFace: "Calibri", align: "center", margin: 0,
      });
      slide.addText(c.stats[i].label, {
        x: sx, y: CARD_Y + 2.07, w: sw, h: 0.22,
        fontSize: 9, color: c.statLabelColor,
        fontFace: "Calibri", align: "center", margin: 0,
      });
    }
  } else {
    slide.addShape(pres.shapes.RECTANGLE, {
      x: tx, y: CARD_Y + 1.68, w: tw, h: 0.72,
      fill: { color: c.statBg },
      line: { color: c.statBg, width: 0 },
    });
    slide.addText(c.stats[0].val, {
      x: tx, y: CARD_Y + 1.76, w: tw, h: 0.32,
      fontSize: 16, bold: true, color: c.statColor,
      fontFace: "Calibri", align: "center", margin: 0,
    });
    slide.addText(c.stats[0].label, {
      x: tx, y: CARD_Y + 2.07, w: tw, h: 0.22,
      fontSize: 9, color: c.statLabelColor,
      fontFace: "Calibri", align: "center", margin: 0,
    });
  }

  // Outcome pill
  slide.addShape(pres.shapes.RECTANGLE, {
    x: tx, y: CARD_Y + 2.92, w: tw, h: 0.36,
    fill: { color: "F2F2F7" },
    line: { color: "F2F2F7", width: 0 },
  });
  slide.addText(c.pillText, {
    x: tx, y: CARD_Y + 2.95, w: tw, h: 0.3,
    fontSize: 9.5, bold: true, color: "3A3A3C",
    fontFace: "Calibri", align: "center", margin: 0,
  });
}

// Bottom takeaway bar
slide.addShape(pres.shapes.RECTANGLE, {
  x: 0.4, y: 4.75, w: 9.2, h: 0.58,
  fill: { color: "FFFFFF" },
  line: { color: "D1D1D6", width: 0.5 },
});

// Green dot
slide.addShape(pres.shapes.OVAL, {
  x: 0.62, y: 4.99, w: 0.1, h: 0.1,
  fill: { color: "34C759" },
  line: { color: "34C759", width: 0 },
});

slide.addText(
  "All three stress tests were absorbed by the system. Performance degraded measurably under fault, but task completion held in every case.",
  {
    x: 0.82, y: 4.78, w: 8.6, h: 0.52,
    fontSize: 11, color: "1D1D1F",
    fontFace: "Calibri", valign: "middle", margin: 0,
  }
);

pres.writeFile({ fileName: "C:\\Users\\Adar\\Desktop\\robotics assignment\\parametric_study_summary.pptx" })
  .then(() => console.log("Saved: parametric_study_summary.pptx"))
  .catch(e => console.error(e));
