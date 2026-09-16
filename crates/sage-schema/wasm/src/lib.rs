//! Exports `sage_schema::validate_manifest` as the `sage:schema/validator` component world.

wit_bindgen::generate!({
    path: "../wit",
    world: "validator",
});

struct Validator;

impl Guest for Validator {
    fn validate_manifest(text: String) -> String {
        sage_schema::validate_manifest(&text).to_json()
    }
}

export!(Validator);
