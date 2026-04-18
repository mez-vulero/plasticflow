# Frappe Desk JS API Reference

## Form Script Triggers

```javascript
frappe.ui.form.on('DocType Name', {
    // Lifecycle
    setup(frm) {},          // once, before form renders
    before_load(frm) {},
    onload(frm) {},         // after form loads
    refresh(frm) {},        // after every refresh (most used)
    onload_post_render(frm) {},
    before_save(frm) {},
    after_save(frm) {},
    before_submit(frm) {},
    on_submit(frm) {},
    before_cancel(frm) {},
    after_cancel(frm) {},
    before_workflow_action(frm) {},
    after_workflow_action(frm) {},

    // Field events
    fieldname(frm) {},           // when field value changes
    'fieldname': function(frm) {},

    // Child table
    'child_table_field.fieldname': function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        // row.fieldname
    }
});
```

---

## frm Object Methods

```javascript
// Field values
frm.set_value('fieldname', value);
frm.get_value('fieldname');            // same as frm.doc.fieldname
frm.set_df_property('fieldname', 'reqd', 1);      // make required
frm.set_df_property('fieldname', 'read_only', 1); // make read only
frm.set_df_property('fieldname', 'hidden', 1);    // hide field
frm.toggle_enable('fieldname', true);
frm.toggle_reqd('fieldname', true);
frm.toggle_display('fieldname', false);

// Query filter on Link field
frm.set_query('link_field', function() {
    return {
        filters: { customer_group: 'Retail' },
        query: 'myapp.queries.get_filtered_customers'  // server-side query
    };
});

// Buttons
frm.add_custom_button('Label', handler);
frm.add_custom_button('Label', handler, 'Group Name');  // grouped
frm.remove_custom_button('Label');
frm.change_custom_button_type('Label', null, 'primary');  // primary/secondary/danger

// Alerts / messages (in form)
frm.dashboard.add_comment('Note text', 'yellow');  // yellow/green/red/blue
frm.set_intro('Intro text', 'blue');
frm.sidebar.add_user_action('Action', handler);

// Child table
let row = frm.add_child('items');  // adds row, returns row object
frappe.model.set_value(row.doctype, row.name, 'fieldname', value);
frm.refresh_field('items');

// Save/submit
frm.save();
frm.savesubmit();
frm.savecancel();
frm.reload_doc();

// Dirty check
frm.is_dirty();

// Attachment
frm.attachments.get_attachments();  // array of attachment docs
```

---

## frappe.db (JS)

```javascript
// Async — returns promise
frappe.db.get_value('Customer', 'CUST-001', 'customer_name')
    .then(r => console.log(r.message.customer_name));

frappe.db.get_value('Customer', {mobile_no: '123'}, ['name', 'email'])

frappe.db.get_list('Item', {
    filters: {disabled: 0},
    fields: ['name', 'item_name'],
    order_by: 'item_name asc',
    limit: 20
}).then(rows => console.log(rows));

frappe.db.get_doc('Customer', 'CUST-001').then(doc => console.log(doc));

frappe.db.set_value('Item', 'ITEM-001', 'rate', 500);

frappe.db.exists('Customer', 'CUST-001').then(exists => {});

frappe.db.count('Item', {disabled: 0}).then(n => {});

frappe.db.delete_doc('ToDo', 'TODO-001');
```

---

## frappe.model (JS)

```javascript
// Get local document (in browser memory)
let doc = frappe.model.get_doc('Customer', 'CUST-001');

// Set value in local model (triggers field events)
frappe.model.set_value('Customer', 'CUST-001', 'customer_name', 'John');

// Child table row
frappe.model.set_value(cdt, cdn, 'fieldname', value);

// Add child row
let row = frappe.model.add_child(frm.doc, 'items');
row.item_code = 'ITEM-001';
frm.refresh_field('items');
```

---

## frappe.call (Server Calls)

```javascript
// Promise-based
await frappe.call({
    method: 'myapp.api.my_method',
    args: { param1: 'value' },
    freeze: true,                  // show loading overlay
    freeze_message: 'Processing...',
    callback(r) {
        // r.message is the return value
    }
});

// Shorthand for document method
await frappe.call({
    method: 'on_submit',
    doc: frm.doc
});
```

---

## Dialogs

```javascript
// Simple alert
frappe.msgprint('Hello World');
frappe.msgprint({
    title: 'Title',
    message: 'Message body',
    indicator: 'green'  // green/red/orange/blue
});

// Confirm
frappe.confirm('Are you sure?', () => {
    // yes callback
}, () => {
    // no callback (optional)
});

// Prompt (simple input)
frappe.prompt('Enter a value', (values) => {
    console.log(values.value);
}, 'Dialog Title', 'Submit');

// Prompt with fields
frappe.prompt([
    {fieldname: 'start_date', fieldtype: 'Date', label: 'Start Date', reqd: 1},
    {fieldname: 'category',   fieldtype: 'Select', label: 'Category',
     options: 'A\nB\nC', default: 'A'}
], (values) => {
    console.log(values.start_date, values.category);
}, 'Enter Details', 'Submit');

// Full Dialog
let d = new frappe.ui.Dialog({
    title: 'My Dialog',
    fields: [
        {fieldname: 'name', fieldtype: 'Data', label: 'Name', reqd: 1},
        {fieldname: 'notes', fieldtype: 'Text', label: 'Notes'},
    ],
    primary_action_label: 'Save',
    primary_action(values) {
        console.log(values);
        d.hide();
    }
});
d.show();

// Get/set dialog field values
d.set_value('name', 'John');
d.get_value('name');
d.fields_dict.name.$input.focus();
```

---

## Notifications / Toasts

```javascript
frappe.show_alert('Saved!', 3);           // 3 seconds
frappe.show_alert({message: 'Done', indicator: 'green'}, 5);
frappe.throw('Validation failed');         // throws + shows red
frappe.msgprint({message: 'Error', indicator: 'red', title: 'Error'});
```

---

## Navigation

```javascript
frappe.set_route('Form', 'Customer', 'CUST-001');
frappe.set_route('List', 'Customer');
frappe.set_route('List', 'Customer', {customer_group: 'Retail'});

// Open new form with defaults
frappe.new_doc('Customer', {customer_group: 'Retail'});

// With callback after form loads
frappe.new_doc('Task', {subject: 'New Task'}, doc => {
    doc.description = 'Do this';
});
```

---

## Realtime (socket.io)

```javascript
// Subscribe to a room/event
frappe.realtime.on('my_event', (data) => {
    console.log('Received:', data);
});

// Python side: publish
# frappe.publish_realtime('my_event', {'key': 'value'}, user=frappe.session.user)
```

---

## Page API (Custom Pages)

```javascript
// myapp/module/page/my_page/my_page.js
frappe.pages['my-page'].on_page_load = function(wrapper) {
    let page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'My Page',
        single_column: true
    });

    page.set_primary_action('New', () => frappe.new_doc('Customer'), 'add');
    page.add_field({fieldname: 'search', fieldtype: 'Data', label: 'Search'});

    $(wrapper).find('.layout-main-section').html('<div id="my-content"></div>');
};
```

---

## Common Utilities

```javascript
frappe.utils.copy_to_clipboard('text');
frappe.utils.filter_dict(list, {'status': 'Open'});
frappe.utils.sum(list, 'amount');
frappe.utils.get_form_link('Customer', 'CUST-001');  // returns HTML <a> tag
frappe.format(value, {fieldtype: 'Currency'});
frappe.datetime.nowdate();       // 'YYYY-MM-DD'
frappe.datetime.now_datetime();  // 'YYYY-MM-DD HH:MM:SS'
frappe.session.user;             // current user email
frappe.user.has_role('System Manager');
```
