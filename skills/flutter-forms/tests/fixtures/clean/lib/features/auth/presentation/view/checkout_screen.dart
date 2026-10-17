import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../view_model/checkout_view_model.dart';

/// MVVM: the Command owns the busy state; the form key is handed to a child that validates it.
class CheckoutScreen extends StatefulWidget {
  const CheckoutScreen({super.key, required this.viewModel});

  final CheckoutViewModel viewModel;

  @override
  State<CheckoutScreen> createState() => _CheckoutScreenState();
}

class _CheckoutScreenState extends State<CheckoutScreen> {
  final _formKey = GlobalKey<FormState>();
  final _cvvController = TextEditingController();
  final _nameController = TextEditingController();

  @override
  void dispose() {
    _cvvController.dispose();
    _nameController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Form(
      key: _formKey,
      child: Column(
        children: [
          TextFormField(
            controller: _nameController,
            textCapitalization: TextCapitalization.words,
            autofillHints: const [AutofillHints.creditCardName],
            validator: (v) => (v == null || v.trim().isEmpty) ? 'Required' : null,
          ),
          TextFormField(
            controller: _cvvController,
            obscureText: true,
            keyboardType: TextInputType.number,
            inputFormatters: [FilteringTextInputFormatter.digitsOnly, LengthLimitingTextInputFormatter(4)],
            decoration: const InputDecoration(labelText: 'CVV'),
          ),
          _SubmitBar(formKey: _formKey, viewModel: widget.viewModel, name: _nameController),
        ],
      ),
    );
  }
}

class _SubmitBar extends StatelessWidget {
  const _SubmitBar({required this.formKey, required this.viewModel, required this.name});

  final GlobalKey<FormState> formKey;
  final CheckoutViewModel viewModel;
  final TextEditingController name;

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: viewModel.pay,
      builder: (context, _) => FilledButton(
        onPressed: viewModel.pay.running
            ? null
            : () {
                if (formKey.currentState!.validate()) viewModel.pay.execute(name.text.trim());
              },
        child: const Text('Pay'),
      ),
    );
  }
}
