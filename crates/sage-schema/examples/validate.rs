//! Prints the validation report for each manifest path given.
fn main() {
    for path in std::env::args().skip(1) {
        let text = std::fs::read_to_string(&path).expect("readable file");
        println!(
            "{path}\n{}\n",
            sage_schema::validate_manifest(&text).to_json()
        );
    }
}
