import { toPng } from 'html-to-image';
import { jsPDF } from 'jspdf';

/**
 * Resolve any CSS color (oklch, hsl, hex, etc.) to [r, g, b]
 * by letting the browser do the conversion via a temporary element.
 */
function cssColorToRgb(color: string): [number, number, number] {
  const el = document.createElement('div');
  el.style.backgroundColor = color;
  el.style.display = 'none';
  document.body.appendChild(el);
  const computed = getComputedStyle(el).backgroundColor;
  document.body.removeChild(el);
  const m = computed.match(/rgba?\(\s*(\d+),\s*(\d+),\s*(\d+)/);
  return m ? [+m[1], +m[2], +m[3]] : [30, 30, 30];
}

function getThemeColors() {
  const root = document.documentElement;
  const isDark = root.classList.contains('dark');

  // Resolve the oklch/hsl background color to RGB via the browser
  const bgVar = getComputedStyle(root).getPropertyValue('--background').trim();
  const bgRgb = bgVar ? cssColorToRgb(bgVar) : (isDark ? [26, 26, 26] : [255, 255, 255]);
  const bgHex = '#' + bgRgb.map(c => c.toString(16).padStart(2, '0')).join('');

  return {
    isDark,
    bgHex,
    bgRgb: bgRgb as [number, number, number],
    titleColor: isDark ? [240, 240, 240] as const : [30, 30, 30] as const,
    subtitleColor: isDark ? [160, 160, 160] as const : [120, 120, 120] as const,
    footerColor: isDark ? [120, 120, 120] as const : [160, 160, 160] as const,
  };
}

export async function exportAnalyticsPDF(
  element: HTMLElement,
  options: { title: string; dateRange: string; orgName?: string }
): Promise<void> {
  const theme = getThemeColors();

  // Capture the chart container — html-to-image handles SVGs correctly
  const imgData = await toPng(element, {
    pixelRatio: 2,
    backgroundColor: theme.bgHex,
    filter: (node) => {
      if (node instanceof HTMLElement && node.style.display === 'none') return false;
      return true;
    },
  });

  const pdf = new jsPDF({ orientation: 'landscape', unit: 'mm', format: 'a4' });

  const pageWidth = pdf.internal.pageSize.getWidth();
  const pageHeight = pdf.internal.pageSize.getHeight();
  const margin = 15;
  const contentWidth = pageWidth - margin * 2;

  // Fill page background with resolved theme color
  pdf.setFillColor(theme.bgRgb[0], theme.bgRgb[1], theme.bgRgb[2]);
  pdf.rect(0, 0, pageWidth, pageHeight, 'F');

  // Header
  pdf.setFontSize(16);
  pdf.setTextColor(theme.titleColor[0], theme.titleColor[1], theme.titleColor[2]);
  pdf.text(options.title, margin, margin + 5);

  pdf.setFontSize(10);
  pdf.setTextColor(theme.subtitleColor[0], theme.subtitleColor[1], theme.subtitleColor[2]);
  pdf.text(
    `${options.dateRange} | Generated ${new Date().toLocaleDateString()}`,
    margin,
    margin + 12,
  );

  // Content image — load to get dimensions
  const img = new Image();
  img.src = imgData;
  await new Promise<void>((resolve) => { img.onload = () => resolve(); });

  const headerOffset = margin + 18;
  const availableHeight = pageHeight - headerOffset - 15; // 15mm footer
  const imgAspect = img.width / img.height;
  let imgWidth = contentWidth;
  let imgHeight = contentWidth / imgAspect;

  if (imgHeight > availableHeight) {
    imgHeight = availableHeight;
    imgWidth = availableHeight * imgAspect;
  }

  pdf.addImage(imgData, 'PNG', margin, headerOffset, imgWidth, imgHeight);

  // Footer
  pdf.setFontSize(8);
  pdf.setTextColor(theme.footerColor[0], theme.footerColor[1], theme.footerColor[2]);
  pdf.text('Powered by Rereflect', pageWidth / 2, pageHeight - 5, { align: 'center' });

  pdf.save(`analytics-${options.dateRange}-${new Date().toISOString().slice(0, 10)}.pdf`);
}
