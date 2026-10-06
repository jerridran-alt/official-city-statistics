import unittest,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from validation_coverage import boundary


class LayoutBoundaryTests(unittest.TestCase):
    def test_multipage_cannot_inherit_single_image_validation(self):
        reason=boundary({'pages':[{'words':[]},{'words':[]}]},{'units':[]})
        self.assertEqual(reason['code'],'MULTIPAGE_LAYOUT_NOT_VALIDATED')
    def test_unread_pages_are_not_complete(self):
        reason=boundary({'pages':[{'words':[]}],'pages_queued':3},{'units':[]})
        self.assertEqual(reason['code'],'INCOMPLETE_PAGE_COVERAGE')
    def test_multiple_city_scan_labels_are_quarantined(self):
        layout={'pages':[{'words':[{'text':'北京市'},{'text':'天津市'},{'text':'52073.4'}]}]}
        self.assertEqual(boundary(layout,{'units':[]})['code'],'MULTICITY_SCAN_LAYOUT_NOT_VALIDATED')
    def test_one_indicator_image_is_not_falsely_blocked_as_city_matrix(self):
        layout={'pages':[{'words':[{'text':'地区生产总值'},{'text':'第二产业'},{'text':'工业'},{'text':'52073.4'}]}]}
        self.assertIsNone(boundary(layout,{'units':[{'id':'110000','name':'北京市'}]}))


if __name__=='__main__':unittest.main()
