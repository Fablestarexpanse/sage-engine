//! Any bytes, read as a PNG card and as a JSON card, must return a report: no panic, no hang,
//! no unbounded allocation.
#![no_main]

use libfuzzer_sys::fuzz_target;

fuzz_target!(|data: &[u8]| {
    let report = sage_schema::card::read_png(data);
    assert_eq!(
        report.ok,
        report.card.is_some()
            && report
                .findings
                .iter()
                .all(|f| f.severity != sage_schema::card::Severity::Error)
    );
    let _ = sage_schema::card::read_json(data);
});
