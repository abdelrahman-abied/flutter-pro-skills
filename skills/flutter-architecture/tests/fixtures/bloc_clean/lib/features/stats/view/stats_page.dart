import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';

import '../../../repositories/todos_repository.dart';
import '../cubit/stats_cubit.dart';
import '../cubit/stats_state.dart';

class StatsPage extends StatelessWidget {
  const StatsPage({super.key});

  @override
  Widget build(BuildContext context) => BlocProvider(
        create: (context) => StatsCubit(context.read<TodosRepository>()),
        child: BlocBuilder<StatsCubit, StatsState>(
          builder: (context, state) => Text('${state.total}'),
        ),
      );
}
