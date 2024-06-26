import argparse
import warnings

import flwr as fl
import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss

import dirichlet_dist as dd
import server as server
import utils

warnings.filterwarnings("ignore")

if __name__ == "__main__":
    random_seed = 42

    parser = argparse.ArgumentParser(description="Flower")
    parser.add_argument(
        "--partition",
        type=int,
        default=0,
        choices=range(0, 11),
        required=False,
        help="Specifies the artificial data partition of the dataset to be used. \
        Picks partition 0 by default",
    )

    parser.add_argument(
        "--num_clients",
        type=int,
        default=10,
        choices=range(1, 11),
        required=False,
        help="Specifies how many clients the bash script will start.",
    )

    args = parser.parse_args()
    # Split train set into 10 partitions and randomly use one for training.
    np.random.seed(random_seed)
    # Subtract one from the id because array's start from 0.
    client_id = args.partition - 1
    num_clients = args.num_clients
    # (X_train, y_train) = utils.partition(X_train, y_train, 10)[client_id]

    data_dist = dd.DirichletDist(
        data_path=server.data_path,
        class_col=server.class_col,
        num_clients=10,
        num_classes=2,
        random_state=random_seed,
        test_split=server.test_split,
    )

    train_data, test_data = data_dist.get_dirichlet_noniid_splits(
        density=server.density
    )

    client_datas = []
    unique_counts = []
    for client_idx in train_data:
        client_datas.append((client_idx, len(train_data[client_idx]["target"])))
        unique_counts.append((client_idx, len(train_data[client_idx]["data"].drop_duplicates())))

    with open(f"client_data_lengts.txt", "w") as f:
        for client_idx, length in client_datas:
            f.write(f"{client_idx + 1}: {length}\n")

    with open(f"client_unique_data_lengts.txt", "w") as f:
        for client_idx, length in unique_counts:
            f.write(f"{client_idx + 1}: {length}\n")

    X_train = train_data[client_id]["data"]
    y_train = train_data[client_id]["target"]

    print(f"Client Data: {X_train.shape}")
    X_test = test_data["data"]
    y_test = test_data["target"]

    if server.plot_client_dist:
        # Create a new figure and axis objects
        fig, axes = plt.subplots(2, 5, figsize=(25, 8))

        # Flatten the axes array to easily access each subplot
        axes = axes.flatten()

        # Plot the figures
        for i in range(10):
            plt.subplot(2, 5, i + 1)
            sns.countplot(x=train_data[i]["target"])
            plt.xlabel('Class')
            plt.ylabel('Count')
            plt.title(f'Class Distribution for Client {i + 1}')

        # Adjust spacing between subplots
        plt.tight_layout()

        # Save the combined figure
        figure_name = 'images/combined_figures_presentation.png'
        plt.savefig(figure_name)

    # Create LogisticRegression Model
    model = LogisticRegression(
        penalty="l2",
        max_iter=server.epochs,  # local epoch
        warm_start=True,  # prevent refreshing weights when fitting
        fit_intercept=True,
    )

    # Setting initial parameters, akin to model.compile for keras models
    utils.set_initial_params(model, n_classes=2, n_features=21)


    # Define Flower client
    class LogisticClient(fl.client.NumPyClient):
        def __init__(self) -> None:
            super().__init__()
            self.curr_round = 1

        def get_parameters(self, config):  # type: ignore
            return utils.get_model_parameters(model)

        def fit(self, parameters, config):  # type: ignore
            utils.set_model_params(model, parameters)
            # Ignore convergence failure due to low local epochs
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                # Get the training data for the current round
                model.fit(X_train, y_train)
                self.curr_round += 1
                if client_id == 6 and self.curr_round == server.num_rounds - 1:
                    feature_importances = model.coef_[0]
                    # Print feature importances
                    # print(f"Feature importances for client {client_id} for round {self.curr_round}:")
                    for feature, importance in zip(X_train.columns, feature_importances):
                        print(f"\n {feature}: {importance}")

                    with open("./client_6_feature_importances.txt", 'w') as file:
                        for feature, importance in zip(X_train.columns, feature_importances):
                            file.write(f"{feature}: {importance}\n")

            # print(f"Training finished for round {config['server_round']}")
            accuracy = model.score(X_test, y_test)
            print(f"Client accuracy for client {client_id}: {accuracy} ")
            return utils.get_model_parameters(model), len(X_train), {}

        def evaluate(self, parameters, config):  # type: ignore
            utils.set_model_params(model, parameters)
            loss = log_loss(y_test, model.predict_proba(X_test))
            accuracy = model.score(X_test, y_test)
            # print(f"Client accuracy for client {client_id}: {accuracy} ")
            return loss, len(X_test), {"accuracy": accuracy}


    # Start Flower client
    fl.client.start_numpy_client(server_address="127.0.0.1:8181", client=LogisticClient())
