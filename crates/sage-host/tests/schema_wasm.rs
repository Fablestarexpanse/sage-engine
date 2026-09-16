//! M2 gate: manifest validation gives byte-identical reports natively and from its WASM build,
//! for every manifest in the sage-schema corpus plus generated edge cases.

use std::path::Path;

use wasmtime::component::{Component, Linker};
use wasmtime::{Config, Engine, Store};

mod bindings {
    wasmtime::component::bindgen!({
        path: "../sage-schema/wit",
        world: "validator",
    });
}

struct Wasm {
    store: Store<()>,
    validator: bindings::Validator,
}

impl Wasm {
    fn new() -> Wasm {
        let engine = Engine::new(&Config::new()).unwrap();
        let component = Component::new(&engine, sage_fixtures::schema_validator()).unwrap();
        let linker = Linker::new(&engine);
        let mut store = Store::new(&engine, ());
        let validator = bindings::Validator::instantiate(&mut store, &component, &linker)
            .expect("the validator needs no imports");
        Wasm { store, validator }
    }

    fn validate(&mut self, text: &str) -> String {
        self.validator
            .call_validate_manifest(&mut self.store, text)
            .unwrap()
    }
}

#[test]
fn wasm_and_native_reports_are_identical() {
    let dir = Path::new(env!("CARGO_MANIFEST_DIR")).join("../sage-schema/tests/corpus");
    let mut inputs: Vec<(String, String)> = std::fs::read_dir(&dir)
        .unwrap()
        .map(|entry| {
            let path = entry.unwrap().path();
            let name = path.file_name().unwrap().to_string_lossy().into_owned();
            (name, std::fs::read_to_string(path).unwrap())
        })
        .collect();
    inputs.sort();
    assert!(inputs.len() >= 20, "corpus went missing");
    inputs.push(("empty".into(), String::new()));
    inputs.push((
        "multibyte text".into(),
        "title: \"\u{e9}\u{6f22}\u{5b57}\u{1f642}\"\n".into(),
    ));
    inputs.push((
        "oversized".into(),
        format!("#{}", "x".repeat(sage_schema::MAX_MANIFEST_BYTES)),
    ));

    let mut wasm = Wasm::new();
    let mut valid = 0;
    for (name, text) in &inputs {
        let native = sage_schema::validate_manifest(text).to_json();
        assert_eq!(wasm.validate(text), native, "{name}");
        valid += usize::from(native.starts_with(r#"{"valid":true"#));
    }
    assert!(
        valid >= 3,
        "corpus should include valid manifests, found {valid}"
    );
    eprintln!(
        "{} manifests identical native and in WASM ({valid} valid)",
        inputs.len()
    );
}
