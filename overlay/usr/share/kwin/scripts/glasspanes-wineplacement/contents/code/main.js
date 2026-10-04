// A Windows program that leaves its position to Windows gets put at the top-left corner by Wine, and
// KWin keeps it there because the position looks deliberate. Centre those, like every other window.
workspace.windowAdded.connect(function (w) {
    if (!w.normalWindow || w.transient || !/\.exe$/i.test(String(w.resourceClass)))
        return;
    var a = workspace.clientArea(KWin.PlacementArea, w);
    var g = w.frameGeometry;
    if (g.x - a.x > 8 || g.y - a.y > 8 || g.width >= a.width || g.height >= a.height)
        return;
    w.frameGeometry = {
        x: a.x + Math.round((a.width - g.width) / 2),
        y: a.y + Math.round((a.height - g.height) / 2),
        width: g.width,
        height: g.height
    };
});
