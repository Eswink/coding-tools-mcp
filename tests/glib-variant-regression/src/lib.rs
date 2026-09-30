#[cfg(test)]
mod tests {
    use glib::prelude::*;

    fn sample() -> glib::Variant {
        ["alpha", "", "中文", "🦀", "omega"].to_variant()
    }

    #[test]
    fn next() {
        let v = sample();
        assert_eq!(v.array_iter_str().unwrap().next(), Some("alpha"));
    }

    #[test]
    fn nth() {
        let v = sample();
        assert_eq!(v.array_iter_str().unwrap().nth(2), Some("中文"));
    }

    #[test]
    fn last() {
        let v = sample();
        assert_eq!(v.array_iter_str().unwrap().last(), Some("omega"));
    }

    #[test]
    fn next_back() {
        let v = sample();
        assert_eq!(v.array_iter_str().unwrap().next_back(), Some("omega"));
    }

    #[test]
    fn nth_back() {
        let v = sample();
        assert_eq!(v.array_iter_str().unwrap().nth_back(1), Some("🦀"));
    }

    #[test]
    fn forward_reverse() {
        let v = sample();
        assert_eq!(v.array_iter_str().unwrap().collect::<Vec<_>>(), ["alpha", "", "中文", "🦀", "omega"]);
        assert_eq!(v.array_iter_str().unwrap().rev().collect::<Vec<_>>(), ["omega", "🦀", "中文", "", "alpha"]);
    }

    #[test]
    fn interleaved() {
        let v = sample();
        let mut it = v.array_iter_str().unwrap();
        assert_eq!(it.size_hint(), (5, Some(5)));
        assert_eq!(it.next(), Some("alpha"));
        assert_eq!(it.next_back(), Some("omega"));
        assert_eq!(it.nth(1), Some("中文"));
        assert_eq!(it.len(), 1);
        assert_eq!(it.nth_back(0), Some("🦀"));
        assert_eq!(it.next(), None);
        assert_eq!(it.next_back(), None);
    }

    #[test]
    fn empty_overflow() {
        let empty: [&str; 0] = [];
        let v = empty.to_variant();
        assert_eq!(v.array_iter_str().unwrap().next(), None);
        assert_eq!(v.array_iter_str().unwrap().next_back(), None);
        assert_eq!(v.array_iter_str().unwrap().last(), None);
        let v = sample();
        let mut it = v.array_iter_str().unwrap();
        assert_eq!(it.nth(usize::MAX), None);
        assert_eq!(it.next(), None);
        let mut it = v.array_iter_str().unwrap();
        assert_eq!(it.nth_back(usize::MAX), None);
        assert_eq!(it.next_back(), None);
    }

    #[test]
    fn strings_borrow_from_variant() {
        let v = sample();
        let (first, last) = {
            let mut it = v.array_iter_str().unwrap();
            (it.next().unwrap(), it.next_back().unwrap())
        };
        assert_eq!((first, last), ("alpha", "omega"));
    }
}
