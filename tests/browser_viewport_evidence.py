"""Viewport evidence only: never present a clipped locator crop as a whole panel."""
import json
from pathlib import Path
from playwright.sync_api import expect


def native_window_contract(root):
    config = json.loads((Path(root) / 'src-tauri/tauri.conf.json').read_text())
    window = config['app']['windows'][0]
    width, height = int(window['minWidth']), int(window['minHeight'])
    assert width > 0 and height > 0
    return {'source': 'src-tauri/tauri.conf.json', 'min_width': width, 'min_height': height}


def viewport_classification(width, height, contract):
    return ('supported_native_window' if width >= contract['min_width'] and height >= contract['min_height']
            else 'diagnostic_outside_native_window_contract')


def visible_control_capture(page, control, path):
    """Scroll real containers, prove intersection, and capture the actual viewport."""
    control.scroll_into_view_if_needed()
    control.evaluate("node => node.scrollIntoView({block:'center',inline:'nearest',behavior:'instant'})")
    expect(control).to_be_visible()
    expect(control).to_be_in_viewport(ratio=0.98)
    enabled = control.is_enabled()
    if enabled:
        # Trial performs actionability checks only; it sends no click/change event.
        control.click(trial=True)
        assert control.evaluate("""node => {
          const r=node.getBoundingClientRect();
          const hit=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);
          return !!hit && (hit===node || node.contains(hit));
        }"""), 'The enabled control is obscured in the viewport'
    page.screenshot(path=str(path), full_page=False, animations='disabled')
    expect(control).to_be_in_viewport(ratio=0.98)
    return {'image': Path(path).name, 'image_scope': 'visible_viewport',
            'control_bounds': control.bounding_box(), 'enabled': enabled,
            'minimum_intersection_ratio': 0.98, 'actionability_checked_without_click': enabled}


def capture_control_viewports(page, panel, root, output, stem, widths, height, controls, report):
    contract = native_window_contract(root)
    report['native_window_contract'] = contract
    report['mobile_visual_acceptance'] = False
    records = report.setdefault('viewport_evidence', [])
    for width in dict.fromkeys(widths):
        page.set_viewport_size({'width': width, 'height': height})
        # Keep the existing narrow-panel overflow assertion, including 390px stress.
        assert panel.evaluate('(e)=>e.scrollWidth<=e.clientWidth+1')
        record = {'width': width, 'height': height,
                  'classification': viewport_classification(width, height, contract),
                  'panel_bounds': panel.bounding_box(), 'checkpoints': []}
        records.append(record)
        for index, (name, control) in enumerate(controls):
            # Preserve the historical filename for the final control checkpoint.
            filename = f'{stem}-{width}.png' if index == len(controls)-1 else f'{stem}-{width}-{name}.png'
            try:
                checkpoint = visible_control_capture(page, control, Path(output)/filename)
                checkpoint['control'] = name
                record['checkpoints'].append(checkpoint)
            except Exception:
                record['failed_checkpoint'] = name
                try:
                    page.screenshot(path=str(Path(output)/f'failed-{stem}-{width}-{name}.png'), full_page=False)
                except Exception:
                    pass
                raise
