package org.tinio.unwritten;

import android.graphics.Canvas;
import android.graphics.ColorFilter;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.PixelFormat;
import android.graphics.Rect;
import android.graphics.RectF;
import android.graphics.drawable.Drawable;

/** Line icons for the Hearth design language (docs/DESIGN.md), drawn
 *  in code: the app builds its whole UI programmatically and carries
 *  no icon assets, so these stay javac-checkable with the rest of it.
 *  Rounded 1.9-unit strokes on a 24-unit grid — the same drawing as
 *  the web app's inline SVGs and the weight of iOS's SF Symbols. */
final class Glyphs extends Drawable {
    static final int RECORD = 1, UPLOAD = 2, LINK = 3, CLOUD = 4, DOWNLOAD = 5,
            SHARE = 6, RETRY = 7, REFRESH = 8, PLAY = 9, CLOSE = 10, TRASH = 11,
            VIDEO = 12, CHEVRON = 13, MIC = 14, BOOK = 15, CAMERA = 16, PAUSE = 17;

    private final int kind;
    private final int sizePx;
    private final Paint stroke = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint fill = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Path path = new Path();

    Glyphs(int kind, int color, int sizePx) {
        this.kind = kind;
        this.sizePx = sizePx;
        stroke.setStyle(Paint.Style.STROKE);
        stroke.setStrokeCap(Paint.Cap.ROUND);
        stroke.setStrokeJoin(Paint.Join.ROUND);
        stroke.setStrokeWidth(1.9f);
        stroke.setColor(color);
        fill.setStyle(Paint.Style.FILL);
        fill.setColor(color);
    }

    void setColor(int color) {
        stroke.setColor(color);
        fill.setColor(color);
        invalidateSelf();
    }

    @Override public int getIntrinsicWidth() { return sizePx; }
    @Override public int getIntrinsicHeight() { return sizePx; }
    @Override public void setAlpha(int alpha) { stroke.setAlpha(alpha); fill.setAlpha(alpha); invalidateSelf(); }
    @Override public void setColorFilter(ColorFilter cf) { stroke.setColorFilter(cf); fill.setColorFilter(cf); invalidateSelf(); }
    @Override public int getOpacity() { return PixelFormat.TRANSLUCENT; }

    @Override public void draw(Canvas c) {
        Rect b = getBounds();
        float s = Math.min(b.width(), b.height()) / 24f;
        if (s <= 0) return;
        c.save();
        c.translate(b.left + (b.width() - 24 * s) / 2f, b.top + (b.height() - 24 * s) / 2f);
        c.scale(s, s);
        path.reset();
        switch (kind) {
            case RECORD:
                c.drawCircle(12, 12, 9, stroke);
                c.drawCircle(12, 12, 4.5f, fill);
                break;
            case UPLOAD:
            case SHARE:
                line(12, 15.5f, 12, 4);
                path.moveTo(7.5f, 8.5f); path.lineTo(12, 4); path.lineTo(16.5f, 8.5f);
                tray(kind == UPLOAD ? 14 : 13);
                c.drawPath(path, stroke);
                break;
            case DOWNLOAD:
                line(12, 4, 12, 15);
                path.moveTo(7.5f, 10.5f); path.lineTo(12, 15); path.lineTo(16.5f, 10.5f);
                line(5, 19.5f, 19, 19.5f);
                c.drawPath(path, stroke);
                break;
            case LINK:
                c.rotate(-45, 12, 12);
                path.addRoundRect(new RectF(2.5f, 9, 13.5f, 15), 3, 3, Path.Direction.CW);
                path.addRoundRect(new RectF(10.5f, 9, 21.5f, 15), 3, 3, Path.Direction.CW);
                c.drawPath(path, stroke);
                break;
            case CLOUD: {
                // The outline of three circles and a base, unioned.
                Path a = new Path(), t = new Path(), r = new Path(), base = new Path();
                a.addCircle(7.5f, 14, 4, Path.Direction.CW);
                t.addCircle(12, 10.5f, 5.5f, Path.Direction.CW);
                r.addCircle(17, 13.75f, 4.25f, Path.Direction.CW);
                base.addRect(7.5f, 13.5f, 17, 18, Path.Direction.CW);
                path.op(a, Path.Op.UNION);
                path.op(t, Path.Op.UNION);
                path.op(r, Path.Op.UNION);
                path.op(base, Path.Op.UNION);
                c.drawPath(path, stroke);
                break;
            }
            case RETRY:
                path.arcTo(new RectF(4, 4, 20, 20), 45, 270, true);
                arrowHead(17.66f, 6.34f, 315);
                c.drawPath(path, stroke);
                break;
            case REFRESH:
                path.arcTo(new RectF(4, 4, 20, 20), 200, 130, true);
                arrowHead(12 + 8 * cos(330), 12 + 8 * sin(330), 330);
                path.arcTo(new RectF(4, 4, 20, 20), 20, 130, true);
                arrowHead(12 + 8 * cos(150), 12 + 8 * sin(150), 150);
                c.drawPath(path, stroke);
                break;
            case PLAY:
                path.moveTo(8, 5.5f); path.lineTo(8, 18.5f); path.lineTo(18.5f, 12); path.close();
                c.drawPath(path, fill);
                break;
            case PAUSE:
                c.drawRoundRect(new RectF(6.5f, 5, 10, 19), 1.2f, 1.2f, fill);
                c.drawRoundRect(new RectF(14, 5, 17.5f, 19), 1.2f, 1.2f, fill);
                break;
            case CLOSE:
                line(6, 6, 18, 18);
                line(18, 6, 6, 18);
                c.drawPath(path, stroke);
                break;
            case TRASH:
                line(4, 7, 20, 7);
                line(10, 11, 10, 17);
                line(14, 11, 14, 17);
                path.moveTo(6, 7); path.lineTo(7, 19.2f); path.quadTo(7.2f, 21, 9, 21);
                path.lineTo(15, 21); path.quadTo(16.8f, 21, 17, 19.2f); path.lineTo(18, 7);
                path.moveTo(9, 7); path.lineTo(9, 4); path.lineTo(15, 4); path.lineTo(15, 7);
                c.drawPath(path, stroke);
                break;
            case VIDEO:
                path.addRoundRect(new RectF(3, 5, 21, 19), 3, 3, Path.Direction.CW);
                path.moveTo(10, 9.5f); path.lineTo(14.5f, 12); path.lineTo(10, 14.5f); path.close();
                c.drawPath(path, stroke);
                break;
            case CHEVRON:
                path.moveTo(9, 5); path.lineTo(16, 12); path.lineTo(9, 19);
                c.drawPath(path, stroke);
                break;
            case MIC:
                path.addRoundRect(new RectF(9, 3, 15, 14), 3, 3, Path.Direction.CW);
                path.arcTo(new RectF(5.5f, 4.5f, 18.5f, 17.5f), 0, 180, true);
                line(12, 17.5f, 12, 21);
                c.drawPath(path, stroke);
                break;
            case BOOK:
                path.addRoundRect(new RectF(5, 3, 19, 21), 2.5f, 2.5f, Path.Direction.CW);
                line(9, 3, 9, 21);
                line(12, 8, 16, 8);
                c.drawPath(path, stroke);
                break;
            case CAMERA:
                path.addRoundRect(new RectF(3, 7, 21, 19), 2.5f, 2.5f, Path.Direction.CW);
                path.moveTo(8, 7); path.lineTo(9.5f, 5); path.lineTo(14.5f, 5); path.lineTo(16, 7);
                path.arcTo(new RectF(8.5f, 9.5f, 15.5f, 16.5f), 200, 150, true);
                arrowHead(12 + 3.5f * cos(350), 13 + 3.5f * sin(350), 350);
                path.arcTo(new RectF(8.5f, 9.5f, 15.5f, 16.5f), 20, 150, true);
                arrowHead(12 + 3.5f * cos(170), 13 + 3.5f * sin(170), 170);
                c.drawPath(path, stroke);
                break;
            default:
                break;
        }
        c.restore();
    }

    private void line(float x1, float y1, float x2, float y2) {
        path.moveTo(x1, y1);
        path.lineTo(x2, y2);
    }

    /** The open box under the upload/share arrow. */
    private void tray(float top) {
        path.moveTo(5, top);
        path.lineTo(5, 17.5f);
        path.arcTo(new RectF(5, 15, 10, 20), 180, -90, false);
        path.lineTo(16.5f, 20);
        path.arcTo(new RectF(14, 15, 19, 20), 90, -90, false);
        path.lineTo(19, top);
    }

    /** Two short strokes at (x, y) pointing along a clockwise arc at
     *  angle deg (screen angles: 0 = east, increasing clockwise). */
    private void arrowHead(float x, float y, float deg) {
        double t = Math.toRadians(deg);
        double dx = -Math.sin(t), dy = Math.cos(t); // clockwise tangent
        for (int side = -1; side <= 1; side += 2) {
            double a = Math.toRadians(180 + side * 40);
            double rx = dx * Math.cos(a) - dy * Math.sin(a);
            double ry = dx * Math.sin(a) + dy * Math.cos(a);
            path.moveTo(x, y);
            path.lineTo((float) (x + rx * 3.6), (float) (y + ry * 3.6));
        }
    }

    private static float cos(float deg) { return (float) Math.cos(Math.toRadians(deg)); }
    private static float sin(float deg) { return (float) Math.sin(Math.toRadians(deg)); }
}
